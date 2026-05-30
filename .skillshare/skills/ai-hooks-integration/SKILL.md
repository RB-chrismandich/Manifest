---
name: ai-hooks-integration
description: |
  Integrate lifecycle hooks across AI coding tools (Claude Code, Gemini CLI, Cursor, OpenCode) and any CLI.
  Use when: (1) installing/removing hooks, (2) creating OpenCode plugins, (3) setting up auto-formatting,
  testing, notifications, security policies, (4) wrapping CLI tools without hooks API.
  Triggers on: "add hook", "install hook", "hook integration", "PreToolUse", "PostToolUse",
  "PermissionRequest", "PostToolUseFailure", "SubagentStart", "SubagentStop", "TeammateIdle",
  "TaskCompleted", "ConfigChange", "WorktreeCreate", "WorktreeRemove", "PreCompact",
  "beforeShellExecution", "auto-format", "notify on complete", "wrap CLI", "intercept command",
  "HTTP hook", "prompt hook", "agent hook", "async hook".
---

# AI Hooks Integration

## Decision Tree

```
Does the target tool have a hooks API?
├── YES (Claude, Gemini CLI, Cursor, OpenCode)
│   └── Installing hooks for multiple tools at once?
│       ├── YES → Use install_all.py
│       │   └── Need cross-tool source detection?
│       │       ├── YES → --unified mode (recommended)
│       │       └── NO  → --command mode (classic)
│       └── NO  → Use single-tool scripts
│           ├── Claude/Gemini/Cursor → merge_hooks.py
│           └── OpenCode → install_opencode_plugin.py
└── NO (gh, aws, kubectl, docker, etc.)
    └── Use install_cli_wrapper.py
```

## Quick Commands

```bash
# Multi-tool: Unified mode (recommended)
scripts/install_all.py --unified --handler "/path/to/handler" --name my-hook

# Multi-tool: Classic mode
scripts/install_all.py --command "/path/to/hook" --name my-hook

# Single tool
scripts/merge_hooks.py --tool claude --path ~/.claude/settings.json --command "<hook>"
scripts/install_opencode_plugin.py --name my-hook --output ~/.config/opencode/plugins

# CLI without hooks API
scripts/install_cli_wrapper.py --cli gh --hook "/path/to/hook"

# Remove
scripts/remove_all.py --command "<hook>" --plugin ~/.config/opencode/plugins/my-hook.js
scripts/remove_cli_wrapper.py --cli gh

# Preview
--dry-run  # Add to any command
```

## Mode Comparison

| Mode | When to Use | Source Detection | Event Filtering |
|------|-------------|------------------|-----------------|
| **Unified** | Multiple AI tools share config files | Auto (process tree) | Yes |
| **Classic** | Single tool or explicit routing | Manual (--source flag) | No |
| **CLI Wrapper** | Tools without hooks API | N/A | N/A |

## Tool Support

| Tool | Config | Events | Hook Types | Has Hooks API |
|------|--------|--------|------------|---------------|
| Claude | `~/.claude/settings.json` | 17 events | command, http, prompt, agent | Yes |
| Gemini CLI | `~/.gemini/settings.json` | 11 events | command | Yes |
| Cursor | `~/.cursor/hooks.json` | 3 events | command | Yes |
| OpenCode | `~/.config/opencode/plugins/*.js` | 10 events | ES module | Yes (plugin) |
| Gemini IDE | N/A | N/A | N/A | **No** |
| gh, aws, etc. | N/A | N/A | N/A | **No** → Use wrapper |

### Claude Code Events (17 total)

SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure,
Notification, SubagentStart, SubagentStop, Stop, TeammateIdle, TaskCompleted, ConfigChange,
WorktreeCreate, WorktreeRemove, PreCompact, SessionEnd

### Gemini CLI Events (11 total)

SessionStart, SessionEnd, BeforeAgent, AfterAgent, BeforeModel, AfterModel, BeforeToolSelection, BeforeTool, AfterTool, PreCompress, Notification

## References

| File | When to Read |
|------|--------------|
| `references/tool-reference.md` | Config paths, events, payload formats, templates |
| `references/use-cases.md` | Hook patterns: security, formatting, testing, notifications |
| `references/unified-hook-usage.md` | Cross-tool interference, source detection, debug |

## Key Behaviors

- **Idempotent**: Duplicates skipped, safe to re-run
- **Safe merge**: Only adds; never overwrites existing hooks
- **Debug**: `HOOK_DEBUG=1` enables logging
