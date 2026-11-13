# Hook Use Cases

Common patterns for AI coding agent hooks across Claude Code, Cursor, and OpenCode.

## Table of Contents

- [Safety & Security](#safety--security)
- [Auto-formatting & Linting](#auto-formatting--linting)
- [Testing](#testing)
- [Notifications](#notifications)
- [Logging & Audit](#logging--audit)
- [Context Injection](#context-injection)
- [CI/CD Integration](#cicd-integration)

---

## Safety & Security

Block dangerous operations before they execute.

### Block Dangerous Commands

**When**: PreToolUse / beforeShellExecution / tool.execute.before / BeforeTool

```bash
#!/bin/bash
# block-dangerous.sh - Block rm -rf, force push, etc.

read -r INPUT
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // .command // ""')

if echo "$COMMAND" | grep -qE 'rm\s+-rf\s+/|git\s+push.*--force|DROP\s+TABLE'; then
  echo '{"continue":false,"decision":"deny","reason":"Blocked: dangerous command"}'
  exit 0
fi

echo '{"continue":true,"decision":"allow"}'
```

**Config (Claude)**:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "/path/to/block-dangerous.sh"}]
    }]
  }
}
```

### Block Sensitive Files

**When**: PreToolUse (Write/Edit/Read tools)

```bash
#!/bin/bash
# block-sensitive.sh - Prevent reading/writing .env, credentials

read -r INPUT
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

if echo "$FILE" | grep -qE '\.(env|pem|key)$|credentials|secrets'; then
  echo '{"continue":false,"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"Blocked: sensitive file"}}'
  exit 0
fi

echo '{"continue":true}'
```

**Config (Claude)**:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Write|Edit|Read",
      "hooks": [{"type": "command", "command": "/path/to/block-sensitive.sh"}]
    }]
  }
}
```

---

## Auto-formatting & Linting

Run formatters after AI edits files.

### Run Formatter on Save

**When**: PostToolUse (Write/Edit) / afterFileEdit / tool.execute.after

```bash
#!/bin/bash
# auto-format.sh - Format files after AI edits

read -r INPUT
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .file_path // ""')

case "$FILE" in
  *.py) python -m black "$FILE" 2>&1 ;;
  *.js|*.ts|*.jsx|*.tsx) npx prettier --write "$FILE" 2>&1 ;;
  *.go) gofmt -w "$FILE" 2>&1 ;;
esac

echo '{"continue":true}'
```

**Config (Claude)**:

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{"type": "command", "command": "/path/to/auto-format.sh"}]
    }]
  }
}
```

### Run Linter

**When**: PostToolUse / afterFileEdit

```bash
#!/bin/bash
# lint-check.sh - Run linter and report issues

read -r INPUT

cd "$(echo "$INPUT" | jq -r '.cwd // "."')"

RESULT=$(npm run lint 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "{\"continue\":true,\"systemMessage\":\"Lint errors:\\n$RESULT\"}"
else
  echo '{"continue":true}'
fi
```

---

## Testing

Run tests after code changes.

### Auto-run Tests

**When**: PostToolUse / afterFileEdit / tool.execute.after

```bash
#!/bin/bash
# auto-test.sh - Run tests after file changes

read -r INPUT
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .file_path // ""')

# Only run tests for source files
if [[ "$FILE" =~ \.(py|js|ts|go)$ ]]; then
  case "$FILE" in
    *.py) RESULT=$(python -m pytest -q 2>&1) ;;
    *.js|*.ts) RESULT=$(npm test 2>&1) ;;
    *.go) RESULT=$(go test ./... 2>&1) ;;
  esac

  echo "{\"continue\":true,\"systemMessage\":\"Test results:\\n$RESULT\"}"
else
  echo '{"continue":true}'
fi
```

### Type Check (TypeScript/Python)

```bash
#!/bin/bash
# type-check.sh

read -r INPUT
cd "$(echo "$INPUT" | jq -r '.cwd // "."')"

RESULT=$(npx tsc --noEmit 2>&1 || python -m mypy . 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "{\"continue\":true,\"systemMessage\":\"Type errors:\\n$RESULT\"}"
else
  echo '{"continue":true}'
fi
```

---

## Notifications

Alert when tasks complete.

### macOS Desktop Notification

**When**: Stop / stop / event (session end)

```bash
#!/bin/bash
# notify-done.sh - macOS notification

osascript -e 'display notification "Task completed" with title "AI Agent" sound name "Glass"'
echo '{"continue":true}'
```

**Config (Cursor)**:

```json
{
  "version": 1,
  "hooks": {
    "stop": [{"command": "/path/to/notify-done.sh"}]
  }
}
```

### Slack Notification

```bash
#!/bin/bash
# slack-notify.sh

WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

read -r INPUT
TOOL=$(echo "$INPUT" | jq -r '.tool_name // "task"')

curl -s -X POST "$WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{\"text\":\"AI agent completed: $TOOL\"}" > /dev/null

echo '{"continue":true}'
```

### Discord Notification

```bash
#!/bin/bash
# discord-notify.sh

WEBHOOK_URL="https://discord.com/api/webhooks/YOUR/WEBHOOK"

read -r INPUT
TOOL=$(echo "$INPUT" | jq -r '.tool_name // "task"')

curl -s -X POST "$WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{\"content\":\"AI agent completed: $TOOL\"}" > /dev/null

echo '{"continue":true}'
```

---

## Logging & Audit

Track AI agent activity.

### Redacted JSONL Audit Log

Use the standard-library logger shipped with this skill for hook input. It reads
the existing JSON event from stdin, recursively redacts common credentials, and
appends one bounded JSONL record. It does not claim tamper-proof storage.

Create a private directory owned by the account running the hook (for example
`~/.ai-audit`, mode `0700`), then set `AI_HOOK_AUDIT_LOG` to a file inside it.
Invoke the logger as a **pre-hook** when logging failure must block the action:

```bash
export AI_HOOK_AUDIT_LOG="$HOME/.ai-audit/events.jsonl"
/path/to/ai-hooks-integration/scripts/runtime/audit_logger.py \
  --path "$AI_HOOK_AUDIT_LOG"
```

The logger requires the variable/path, rejects unsafe parents/files, and fails
closed on invalid, oversized, or unredactable input; it emits no success
response. Keep the path parent owned by the effective user and not
group/world-writable. It redacts Bearer credentials, password/token command
arguments, `*_TOKEN=` assignments, and URL userinfo, while preserving the
original event structure. Treat logs as sensitive data despite redaction.

For native hook protocols that require a response on stdout, use an adapter
that invokes this logger and emits the protocol's success response only after
the logger exits successfully; do not pipe raw events to a plain append command.

### Compliance Audit Trail

Use the same logger and path policy above rather than appending raw hook input.
Keep each invocation as a separate JSONL record; configure it as a pre-hook
when audit-write failure must prevent the operation.

---

## Context Injection

Add context before operations.

### Add Git Status to Prompts

**When**: UserPromptSubmit / chat.message / BeforeTool / BeforeAgent

```bash
#!/bin/bash
# add-git-context.sh

read -r INPUT

GIT_STATUS=$(git status --short 2>/dev/null)
GIT_BRANCH=$(git branch --show-current 2>/dev/null)

if [ -n "$GIT_STATUS" ]; then
  CONTEXT="Current branch: $GIT_BRANCH\nModified files:\n$GIT_STATUS"
  echo "{\"continue\":true,\"systemMessage\":\"$CONTEXT\"}"
else
  echo '{"continue":true}'
fi
```

### Add Project Context

```bash
#!/bin/bash
# project-context.sh - Add project info to context

read -r INPUT

# Read project description if exists
if [ -f "README.md" ]; then
  SUMMARY=$(head -50 README.md)
  echo "{\"continue\":true,\"systemMessage\":\"Project context:\\n$SUMMARY\"}"
else
  echo '{"continue":true}'
fi
```

---

## CI/CD Integration

Trigger CI/CD workflows.

### Trigger GitHub Actions

**When**: Stop / tool.execute.after (for specific tools)

```bash
#!/bin/bash
# trigger-ci.sh

REPO="owner/repo"
WORKFLOW="test.yml"
TOKEN="${GITHUB_TOKEN}"

curl -s -X POST \
  "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"ref":"main"}' > /dev/null

echo '{"continue":true}'
```

### Auto-commit Changes

**When**: Stop (be careful with this)

```bash
#!/bin/bash
# auto-commit.sh - Commit AI changes

read -r INPUT

cd "$(echo "$INPUT" | jq -r '.cwd // "."')"

if git diff --quiet; then
  echo '{"continue":true}'
  exit 0
fi

git add -A
git commit -m "AI agent: auto-commit changes"

echo '{"continue":true,"systemMessage":"Changes committed"}'
```

---

## Claude Code Advanced Patterns

New patterns using Claude Code's expanded hook system (17 events, 4 hook types).

### HTTP Hook: External Validation Service

**When**: PreToolUse - validate commands against a remote policy engine

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "http",
        "url": "http://localhost:8080/hooks/validate",
        "headers": {"Authorization": "Bearer $POLICY_TOKEN"},
        "allowedEnvVars": ["POLICY_TOKEN"],
        "timeout": 10
      }]
    }]
  }
}
```

### Prompt Hook: AI-Powered Stop Gate

**When**: Stop - LLM evaluates if all tasks are truly complete

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "prompt",
        "prompt": "Evaluate if Claude should stop: $ARGUMENTS. Check: 1) All tasks complete 2) No errors 3) No follow-up needed. Respond {\"ok\":true} or {\"ok\":false,\"reason\":\"...\"}",
        "timeout": 30
      }]
    }]
  }
}
```

### Agent Hook: Verify Tests Pass Before Stop

**When**: Stop - subagent runs tests and inspects results

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "agent",
        "prompt": "Run the test suite and verify all tests pass before allowing Claude to stop. $ARGUMENTS",
        "timeout": 120
      }]
    }]
  }
}
```

### Async Hook: Background Test Runner

**When**: PostToolUse - run tests in background after file changes

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{
        "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/run-tests-async.sh",
        "async": true,
        "timeout": 300
      }]
    }]
  }
}
```

### TaskCompleted: Enforce Quality Gates

**When**: TaskCompleted - prevent task completion without passing tests

```bash
#!/bin/bash
# task-quality-gate.sh
INPUT=$(cat)
TASK_SUBJECT=$(echo "$INPUT" | jq -r '.task_subject')

if ! npm test 2>&1; then
  echo "Tests not passing. Fix before completing: $TASK_SUBJECT" >&2
  exit 2
fi
exit 0
```

### ConfigChange: Audit Settings Changes

**When**: ConfigChange - log all config modifications

```bash
#!/bin/bash
# audit-config.sh
INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source')
FILE=$(echo "$INPUT" | jq -r '.file_path // "N/A"')
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Config changed: $SOURCE ($FILE)" >> ~/.ai-audit/config.log

# Block non-admin changes to project settings
if [ "$SOURCE" = "project_settings" ] && [ ! -f ".claude/admin-approved" ]; then
  echo '{"decision": "block", "reason": "Project settings require admin approval"}'
fi
```

### PermissionRequest: Auto-Approve Safe Commands

**When**: PermissionRequest - approve known-safe commands automatically

```bash
#!/bin/bash
# auto-approve.sh
INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Auto-approve safe read-only commands
if [ "$TOOL" = "Bash" ] && echo "$CMD" | grep -qE '^(ls|cat|echo|git status|npm test|go test)'; then
  jq -n '{hookSpecificOutput:{hookEventName:"PermissionRequest",decision:{behavior:"allow"}}}'
  exit 0
fi

# Let user decide for everything else
exit 0
```

### SessionStart: Persist Environment Variables

**When**: SessionStart - set up environment for entire session

```bash
#!/bin/bash
# setup-env.sh
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo 'export NODE_ENV=development' >> "$CLAUDE_ENV_FILE"
  echo 'export PATH="$PATH:./node_modules/.bin"' >> "$CLAUDE_ENV_FILE"
fi
exit 0
```

### MCP Tool Hooks

**When**: PreToolUse/PostToolUse - monitor or control MCP server tools

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__memory__.*",
        "hooks": [{"type": "command", "command": "echo 'Memory op' >> ~/mcp.log"}]
      },
      {
        "matcher": "mcp__.*__write.*",
        "hooks": [{"type": "command", "command": "/path/to/validate-mcp-write.py"}]
      }
    ]
  }
}
```

### Skill/Agent Frontmatter Hooks

Hooks scoped to a skill's lifetime:

```yaml
---
name: secure-operations
description: Perform operations with security checks
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/security-check.sh"
          once: true
---
```

---

## Cross-Tool Implementation

### OpenCode Plugin Example

```js
// ~/.config/opencode/plugins/auto-format.js
// Note: Uses spawn for safe subprocess execution

const { spawn } = require("child_process");
const path = require("path");

function runCommand(cmd, args) {
  return new Promise((resolve) => {
    const proc = spawn(cmd, args, { stdio: "ignore" });
    proc.on("close", resolve);
    proc.on("error", resolve);
  });
}

module.exports = async function AutoFormatPlugin(pluginInput) {
  return {
    "tool.execute.after": async (input, output) => {
      if (input.tool !== "write" && input.tool !== "edit") return;

      const filePath = output?.args?.file_path;
      if (!filePath) return;

      const ext = path.extname(filePath);
      try {
        switch (ext) {
          case ".py":
            await runCommand("python", ["-m", "black", filePath]);
            break;
          case ".js":
          case ".ts":
            await runCommand("npx", ["prettier", "--write", filePath]);
            break;
        }
      } catch (e) {
        console.error("Auto-format failed:", e.message);
      }
    },
  };
};
```

### Multi-Tool Script

```bash
#!/bin/bash
# universal-hook.sh - Detect source and adapt behavior

read -r INPUT

# Detect which tool called us
if echo "$INPUT" | jq -e '.hookSpecificOutput' > /dev/null 2>&1; then
  SOURCE="claude"
elif echo "$INPUT" | jq -e '.version' > /dev/null 2>&1; then
  SOURCE="cursor"
else
  echo "unrecognized hook source" >&2
  exit 1
fi

# Extract command regardless of format
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // .command // .args.command // ""')

# Common logic
if echo "$COMMAND" | grep -q 'rm -rf'; then
  case "$SOURCE" in
    claude)
      echo '{"continue":false,"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"Blocked"}}'
      ;;
    cursor)
      echo '{"continue":false,"permission":"deny","user_message":"Blocked"}'
      ;;
  esac
  exit 0
fi

echo '{"continue":true,"decision":"allow"}'
```
