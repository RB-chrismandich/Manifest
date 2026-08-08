---
name: ai-hooks-integration
description: Integrate lifecycle hooks across AI coding tools (Claude Code, Gemini CLI, Cursor, OpenCode) — adding/installing hooks, OpenCode plugins, auto-format/notify/security policies, or wrapping CLIs without a hooks API. Covers PreToolUse/PostToolUse and HTTP/prompt/agent/async hooks.
---

# AI Hooks Integration

## Decision Tree

```text
Does the target tool have a hooks API?
├── YES (Claude, Gemini CLI, Cursor, OpenCode)
│   └── Installing hooks for multiple tools at once?
│       ├── YES → Use install_all.py
│       │   ├── One normalizer per native target → --unified mode
│       │   └── Tool-specific command → --command mode
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
scripts/merge_hooks.py --tool claude --path "$(native Claude settings path)" --command "<hook>"
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

| Mode | When to Use | Source Routing | Event Filtering |
|------|-------------|------------------|-----------------|
| **Unified** | Same normalizer across native targets | Explicit per target | Yes |
| **Classic** | Single tool or explicit routing | Manual (--source flag) | No |
| **CLI Wrapper** | Tools without hooks API | N/A | N/A |

## Tool Support

| Tool | Config | Events | Hook Types | Has Hooks API |
|------|--------|--------|------------|---------------|
| Claude | `~/.claude/settings.json` | See reference | command, http, prompt, agent | Yes |
| Gemini CLI | `~/.gemini/settings.json` | See reference | command | Yes |
| Cursor | `~/.cursor/hooks.json` | See reference | command | Yes |
| OpenCode | `~/.config/opencode/plugins/*.js` | See reference | ES module | Yes (plugin) |
| Gemini IDE | N/A | N/A | N/A | **No** |
| gh, aws, etc. | N/A | N/A | N/A | **No** → Use wrapper |

Full event lists per tool: `references/tool-reference.md`.

## References

| File | When to Read |
|------|--------------|
| `references/tool-reference.md` | Config paths, events, payload formats, templates |
| `references/use-cases.md` | Hook patterns: security, formatting, testing, notifications |
| `references/unified-hook-usage.md` | Cross-tool interference, source detection, debug |

## Key Behaviors

- **Idempotent**: Duplicates skipped, safe to re-run
- **Safe merge**: Adds ownership-marked entries and preserves unrelated hooks
- **Native isolation**: Each harness reads and writes only its own target
- **Degradation**: Unsupported hook events return a structured degraded result
- **Debug**: `HOOK_DEBUG=1` enables logging
