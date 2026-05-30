# Tool Reference

Complete reference for all supported tools: config paths, events, payloads, templates.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Claude Code](#claude-code)
- [Gemini CLI](#gemini-cli)
- [Cursor](#cursor)
- [OpenCode](#opencode)
- [CLI Wrapper](#cli-wrapper)
- [Field Mapping](#field-mapping)

---

## Quick Reference

| Tool | Config | Events | Hook Types | Nesting |
|------|--------|--------|------------|---------|
| Claude | `~/.claude/settings.json` | 17 | command, http, prompt, agent | nested |
| Gemini | `~/.gemini/settings.json` | 11 | command | nested |
| Cursor | `~/.cursor/hooks.json` | 3 | command | flat |
| OpenCode | `~/.config/opencode/plugins/*.js` | 10 | ES module | plugin |

---

## Claude Code

### Config Locations (Priority)

| Location | Scope | Shareable |
|----------|-------|-----------|
| `~/.claude/settings.json` | All projects | No |
| `.claude/settings.json` | Single project | Yes (commit) |
| `.claude/settings.local.json` | Single project | No (gitignored) |
| Managed policy | Organization | Admin-controlled |
| Plugin `hooks/hooks.json` | When plugin enabled | Yes |
| Skill/agent frontmatter | While component active | Yes |

### Events (17 total)

| Event | Matcher | Can Block | Hook Types | Description |
|-------|---------|-----------|------------|-------------|
| SessionStart | ✓ `startup\|resume\|clear\|compact` | ✗ | cmd | Session begins/resumes |
| UserPromptSubmit | ✗ | ✓ | cmd,http,prompt,agent | Before prompt processed |
| PreToolUse | ✓ tool name regex | ✓ | cmd,http,prompt,agent | Before tool execution |
| PermissionRequest | ✓ tool name regex | ✓ | cmd,http,prompt,agent | Permission dialog shown |
| PostToolUse | ✓ tool name regex | ✗ (feedback) | cmd,http,prompt,agent | After tool succeeds |
| PostToolUseFailure | ✓ tool name regex | ✗ (feedback) | cmd,http,prompt,agent | After tool fails |
| Notification | ✓ type | ✗ | cmd | Notification sent |
| SubagentStart | ✓ agent type | ✗ | cmd | Subagent spawned |
| SubagentStop | ✓ agent type | ✓ | cmd,http,prompt,agent | Subagent finished |
| Stop | ✗ | ✓ | cmd,http,prompt,agent | Claude finishes responding |
| TeammateIdle | ✗ | ✓ (exit 2) | cmd | Teammate about to idle |
| TaskCompleted | ✗ | ✓ (exit 2) | cmd,http,prompt,agent | Task marked completed |
| ConfigChange | ✓ source | ✓ | cmd | Config file changes |
| WorktreeCreate | ✗ | ✓ (non-zero) | cmd | Worktree being created |
| WorktreeRemove | ✗ | ✗ | cmd | Worktree being removed |
| PreCompact | ✓ `manual\|auto` | ✗ | cmd | Before context compaction |
| SessionEnd | ✓ reason | ✗ | cmd | Session terminates |

Matcher patterns: `"Bash"` (exact), `"Write|Edit"` (OR regex), `"mcp__memory__.*"` (MCP), `"*"` or omit (all).

### Hook Types (4)

| Type | Field | Description | Async? |
|------|-------|-------------|--------|
| `command` | `command` | Shell command, stdin=JSON, stdout=JSON | ✓ |
| `http` | `url` | POST JSON to URL, response=JSON | ✗ |
| `prompt` | `prompt` | Single-turn LLM evaluation → `{ok, reason}` | ✗ |
| `agent` | `prompt` | Multi-turn subagent with Read/Grep/Glob → `{ok, reason}` | ✗ |

### Common Handler Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | ✓ | `"command"`, `"http"`, `"prompt"`, `"agent"` |
| `timeout` | ✗ | Seconds (defaults: cmd=600, prompt=30, agent=60) |
| `statusMessage` | ✗ | Custom spinner message |
| `once` | ✗ | Run once per session (skills only) |
| `async` | ✗ | Background execution (command only) |

### Environment Variables

```bash
CLAUDE_PROJECT_DIR     # Project root (use in command paths)
CLAUDE_PLUGIN_ROOT     # Plugin root (for plugin-bundled scripts)
CLAUDE_ENV_FILE        # Write exports here to persist env vars (SessionStart only)
CLAUDE_CODE_REMOTE     # "true" in remote web environments
```

### Common Input Fields (all events)

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../transcript.jsonl",
  "cwd": "/project",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse"
}
```

### Common Output Fields (JSON on stdout, exit 0)

| Field | Default | Description |
|-------|---------|-------------|
| `continue` | `true` | `false` = stop Claude entirely |
| `stopReason` | - | Message to user when `continue: false` |
| `suppressOutput` | `false` | Hide stdout from verbose mode |
| `systemMessage` | - | Warning shown to user |

### Exit Codes

| Code | Meaning | Behavior |
|------|---------|----------|
| 0 | Success | Parse stdout as JSON |
| 2 | Block | stderr → error to Claude; blocks tool (PreToolUse) / prompt (UserPromptSubmit) / stop (Stop) |
| Other | Warning | Non-blocking, continues |

### Config Template

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "<hook>"}]}
    ]
  }
}
```

### PreToolUse I/O

**Input:**
```json
{
  "tool_name": "Bash",
  "tool_input": {"command": "npm test", "description": "Run tests", "timeout": 120000},
  "tool_use_id": "toolu_01ABC...",
  "session_id": "...", "cwd": "/project", "permission_mode": "default",
  "hook_event_name": "PreToolUse"
}
```

**Allow:**
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "permissionDecisionReason": "Safe"}}
```

**Deny:**
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked"}}
```

**Ask user:**
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": "Needs review"}}
```

**Modify input + allow:**
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": {"command": "npm test --coverage"}}}
```

**Add context:**
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "Running in production"}}
```

### PermissionRequest I/O

**Input:**
```json
{
  "tool_name": "Bash", "tool_input": {"command": "rm -rf node_modules"},
  "permission_suggestions": [{"type": "toolAlwaysAllow", "tool": "Bash"}],
  "hook_event_name": "PermissionRequest"
}
```

**Allow:**
```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
```

**Allow + modify + remember:**
```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow", "updatedInput": {"command": "npm run lint"}, "updatedPermissions": [{"type": "toolAlwaysAllow", "tool": "Bash"}]}}}
```

**Deny:**
```json
{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "deny", "message": "Not allowed", "interrupt": true}}}
```

### PostToolUse I/O

**Input:**
```json
{
  "tool_name": "Write",
  "tool_input": {"file_path": "/path/file.txt", "content": "..."},
  "tool_response": {"filePath": "/path/file.txt", "success": true},
  "tool_use_id": "toolu_01ABC...",
  "hook_event_name": "PostToolUse"
}
```

**Feedback to Claude:**
```json
{"decision": "block", "reason": "Linting errors found", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "Fix ESLint errors"}}
```

**Replace MCP tool output:**
```json
{"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedMCPToolOutput": "filtered result"}}
```

### PostToolUseFailure I/O

**Input:**
```json
{
  "tool_name": "Bash", "tool_input": {"command": "npm test"},
  "tool_use_id": "toolu_01ABC...",
  "error": "Command exited with non-zero status code 1",
  "is_interrupt": false,
  "hook_event_name": "PostToolUseFailure"
}
```

### Stop / SubagentStop I/O

**Input:**
```json
{
  "stop_hook_active": false,
  "last_assistant_message": "I've completed the refactoring...",
  "hook_event_name": "Stop"
}
```

SubagentStop adds: `agent_id`, `agent_type`, `agent_transcript_path`.

**Block (continue working):**
```json
{"decision": "block", "reason": "Tests still failing, please fix"}
```

### SessionStart I/O

**Input:**
```json
{"source": "startup", "model": "claude-sonnet-4-6", "hook_event_name": "SessionStart"}
```

**Inject context (plain text stdout or JSON):**
```json
{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Project uses Python 3.12"}}
```

**Persist env vars:** Write to `$CLAUDE_ENV_FILE`:
```bash
echo 'export NODE_ENV=production' >> "$CLAUDE_ENV_FILE"
```

### UserPromptSubmit I/O

**Input:**
```json
{"prompt": "Delete the database", "hook_event_name": "UserPromptSubmit"}
```

**Block:**
```json
{"decision": "block", "reason": "Destructive prompts not allowed"}
```

### TeammateIdle / TaskCompleted

Exit code 2 + stderr to block. No JSON decision control.

### ConfigChange I/O

**Input:** `source` = `user_settings|project_settings|local_settings|policy_settings|skills`, `file_path`.

**Block:** `{"decision": "block", "reason": "..."}` (policy_settings cannot be blocked).

### WorktreeCreate / WorktreeRemove

**Create input:** `name` (slug). **Output:** stdout = absolute path to created worktree.
**Remove input:** `worktree_path`. No decision control.

### Prompt/Agent Hook Response

```json
{"ok": true}
{"ok": false, "reason": "Tests not passing"}
```

### HTTP Hook

```json
{
  "type": "http",
  "url": "http://localhost:8080/hooks/pre-tool-use",
  "headers": {"Authorization": "Bearer $MY_TOKEN"},
  "allowedEnvVars": ["MY_TOKEN"],
  "timeout": 30
}
```

Non-2xx = non-blocking error. Block via 2xx + JSON `decision: "block"`.

### Async Hook

```json
{
  "type": "command",
  "command": "/path/to/tests.sh",
  "async": true,
  "timeout": 300
}
```

Cannot block; `systemMessage`/`additionalContext` delivered on next turn.

---

## Gemini CLI

### Config Locations (Priority)

1. Project: `.gemini/settings.json`
2. User: `~/.gemini/settings.json`
3. System: `/etc/gemini-cli/settings.json`

### Events

| Event | Matcher | Description | Influence |
|-------|---------|-------------|-----------|
| SessionStart | ✗ | Session begins (startup/resume/clear) | Inject context |
| SessionEnd | ✗ | Session ends (exit/clear) | Advisory |
| BeforeAgent | ✗ | After user prompt, before planning | Block turn / context |
| AfterAgent | ✗ | Agent loop ends | Retry / halt |
| BeforeModel | ✗ | Before LLM request | Block / mock |
| AfterModel | ✗ | After LLM response | Filter / redact |
| BeforeToolSelection | ✗ | Before tool selection | Filter tools |
| BeforeTool | ✓ | Before tool execution | Validate / block |
| AfterTool | ✓ | After tool execution | Process / hide |
| PreCompress | ✗ | Before context compression | Advisory |
| Notification | ✗ | System notification | Advisory |

Matcher: regex for tool events (`BeforeTool`, `AfterTool`), exact string for lifecycle.

### Config Template

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "write_file|replace",
        "hooks": [
          {
            "name": "security-check",
            "type": "command",
            "command": "$GEMINI_PROJECT_DIR/.gemini/hooks/security.sh",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

### Hook Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | ✓ | Execution engine (only `"command"`) |
| `command` | ✓ | Shell command to execute |
| `name` | ✗ | Friendly identifier for logs/CLI |
| `timeout` | ✗ | Timeout in ms (default: 60000) |
| `description` | ✗ | Brief explanation |

### Environment Variables

```bash
GEMINI_PROJECT_DIR   # Project root absolute path
GEMINI_SESSION_ID    # Current session unique ID
GEMINI_CWD           # Current working directory
CLAUDE_PROJECT_DIR   # Compatibility alias
```

### Exit Codes

| Code | Meaning | Behavior |
|------|---------|----------|
| 0 | Success | Preferred for all logic (including deny) |
| 2 | System block | Critical abort |
| Other | Warning | Non-fatal, continues with original params |

**Golden Rule**: stdout must be valid JSON. Use stderr for debug.

### BeforeTool I/O

**Input:**
```json
{
  "hook_name": "BeforeTool",
  "tool_name": "run_shell_command",
  "tool_input": {"command": "ls"},
  "session_id": "..."
}
```

**Allow:**
```json
{"decision": "allow"}
```

**Allow + Context:**
```json
{"decision": "allow", "systemMessage": "Extra context"}
```

**Deny:**
```json
{"decision": "deny", "reason": "Blocked", "systemMessage": "..."}
```

### SessionStart I/O

**Input:**
```json
{"hook_name": "SessionStart", "session_id": "...", "trigger": "startup"}
```

**Output:**
```json
{"systemMessage": "Context injected at session start"}
```

### Managing Hooks (CLI)

```bash
/hooks panel           # View all hooks
/hooks enable-all      # Enable all
/hooks disable-all     # Disable all
/hooks enable <name>   # Enable specific hook
/hooks disable <name>  # Disable specific hook
```

---

## Cursor

### Events

| Event | Description |
|-------|-------------|
| beforeShellExecution | Before shell command |
| afterFileEdit | After file modified |
| stop | Task completes |

### Config Template

```json
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [{"command": "<hook>"}]
  }
}
```

### beforeShellExecution I/O

**Input:**
```json
{"command": "ls", "cwd": "/project"}
```

**Allow:**
```json
{"continue": true, "permission": "allow"}
```

**Deny:**
```json
{"continue": false, "permission": "deny", "agent_message": "Blocked"}
```

---

## OpenCode

**Critical**: Plugin must export a **function**, not an object.

### Plugin Locations

- Project: `.opencode/plugins/`
- Global: `~/.config/opencode/plugins/`
- npm: Add to `opencode.json` `plugin` array

### Events

| Event | Description |
|-------|-------------|
| tool.execute.before | Before tool execution |
| tool.execute.after | After tool execution |
| command.executed | After command runs |
| file.edited | File was edited |
| file.watcher.updated | File watcher triggered |
| session.created | Session started |
| session.idle | Session became idle |
| session.compacted | Context compressed |
| permission.ask | Permission requested |
| chat.message | Chat message sent |
| event | All events (passive) |

### Context Object

```js
export const MyPlugin = async ({ project, client, $, directory, worktree }) => {
  // project: current project info
  // client: OpenCode SDK client
  // $: Bun shell API (for running commands)
  // directory: working directory
  // worktree: git worktree path
  return { /* hooks */ };
};
```

### Plugin Template

```js
export const MyPlugin = async ({ directory, $ }) => {
  return {
    "tool.execute.before": async (input, output) => {
      // input.tool, input.sessionID, input.callID
      // output.args (mutable)
      if (input.tool === "read" && output.args.filePath?.includes(".env")) {
        throw new Error("Blocked: .env files");  // throw to block
      }
    },

    "tool.execute.after": async (input, output) => {
      // output.title, output.output, output.metadata
      console.log(`Completed: ${input.tool}`);
    },

    "event": async ({ event }) => {
      if (event.type === "session.idle") {
        await $`osascript -e 'display notification "Done!"'`;
      }
    },
  };
};
```

### All Available Hooks

```js
{
  "tool.execute.before": async (input, output) => {},
  "tool.execute.after": async (input, output) => {},
  "command.execute.before": async (input, output) => {},
  "chat.message": async (input, output) => {},
  "chat.params": async (input, output) => {},
  "chat.headers": async (input, output) => {},  // add custom headers
  "permission.ask": async (input, output) => {},
  "event": async ({ event }) => {},
  "config": async (config) => {},  // modify config
}
```

---

## CLI Wrapper

For tools **without** hooks API (gh, aws, kubectl, docker).

### Flow

```
User → ~/.local/bin/gh (wrapper) → Pre-hook → /usr/bin/gh → Post-hook → Exit
```

### Install

```bash
scripts/install_cli_wrapper.py --cli gh --hook "/path/to/hook"
```

### Pre-hook I/O

**Input:**
```json
{"cli": "gh", "args": ["pr", "create"], "cwd": "/project", "phase": "pre"}
```

**Allow:** Exit 0 or `{"decision": "allow"}`

**Deny:**
```json
{"decision": "deny", "reason": "Blocked"}
```

### Post-hook I/O

**Input:**
```json
{"cli": "gh", "args": ["pr", "create"], "cwd": "/project", "phase": "post", "exit_code": 0}
```

### Templates

| Template | Dependencies | JSON I/O |
|----------|--------------|----------|
| bash | jq | Yes |
| python | None | Yes |
| minimal | None | No (CLI args) |

---

## Field Mapping

### Input Fields

| Field | Claude | Gemini | Cursor | OpenCode |
|-------|--------|--------|--------|----------|
| Tool name | `tool_name` | `tool_name` | - | `input.tool` |
| Command | `tool_input.command` | `tool_input.command` | `command` | `output.args.command` |
| CWD | `cwd` | `$GEMINI_CWD` (env) | `cwd` | `ctx.directory` |
| Session | `session_id` | `session_id` / `$GEMINI_SESSION_ID` | - | `input.sessionID` |
| Project | `cwd` | `$GEMINI_PROJECT_DIR` (env) | - | `ctx.worktree` |

### Output Fields

| Action | Claude | Gemini | Cursor | OpenCode |
|--------|--------|--------|--------|----------|
| Allow | `permissionDecision: "allow"` | `decision: "allow"` | `permission: "allow"` | return |
| Deny | `permissionDecision: "deny"` | `decision: "deny"` | `permission: "deny"` | throw |
| Message | `systemMessage` | `systemMessage` | `agent_message` | console.log |

---

## External Docs

- Claude: https://code.claude.com/docs/en/hooks
- Gemini: https://geminicli.com/docs/hooks/
- Cursor: https://docs.cursor.com/agent/hooks
