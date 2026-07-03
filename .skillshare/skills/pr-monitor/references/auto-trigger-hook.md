# Auto-trigger hook: run the monitor when a PR is created

This skill can fire automatically the moment you open a PR/MR from an AI coding
tool. The trigger is a **tool-lifecycle hook** (Claude Code PostToolUse and the
equivalents in Cursor, Gemini CLI, and Antigravity) that watches shell commands
for a successful `gh pr create` / `glab mr create` and then nudges the agent to
run `pr-monitor` on the new PR.

It is *not* a git hook: PR/MR creation is a remote event, and a git hook can't
see it. It's also not server-side CI — it runs inside your AI session, where the
"address the findings" half of this workflow actually lives.

## How it works

```text
you run: gh pr create / glab mr create
            │ (tool succeeds)
            ▼
PostToolUse / AfterTool / afterShellExecution hook
            │ stdin = tool payload (JSON)
            ▼
scripts/pr_create_trigger.py
            │ matches `gh pr create` | `glab mr create` AND success?
            ├── no  → prints nothing, exit 0   (fail-open: never blocks you)
            └── yes → emits additionalContext telling the agent to run the skill
```

The handler is **fail-open**: malformed payloads, non-matching commands, and
failed PR creations all produce no output and exit 0, so the hook can never
wedge your normal workflow.

## Install across all four tools (recommended)

Use the `ai-hooks-integration` skill's unified installer — one handler, source
detection, registered on the right event for each tool:

```bash
HANDLER="$HOME/.claude/skills/pr-monitor/scripts/pr_create_trigger.py"

~/.claude/skills/ai-hooks-integration/scripts/install_all.py \
  --unified \
  --handler "$HANDLER" \
  --name pr-monitor \
  --dry-run        # drop --dry-run to apply
```

Unified mode registers the handler on each tool's tool-lifecycle event and
normalizes the payload; the handler (`pr_create_trigger.py`) does its own
filtering — it only acts on a successful `gh pr create` / `glab mr create` and
no-ops on everything else, so there's no per-event/matcher flag to set.

This registers the equivalent event per tool:

| Tool        | Config                          | Event                   |
|-------------|---------------------------------|-------------------------|
| Claude Code | `~/.claude/settings.json`       | PostToolUse (Bash)      |
| Gemini CLI  | `~/.gemini/settings.json`       | AfterTool               |
| Cursor      | `~/.cursor/hooks.json`          | afterShellExecution     |
| Antigravity | symlinks to `~/.claude/` config | (covered via Claude)    |

In this repo, Antigravity's config is symlinked to Claude's (`configs/antigravity/`
→ `../claude/`), so the Claude hook covers Antigravity. OpenCode, if used, takes
a plugin instead — see `install_opencode_plugin.py` in ai-hooks-integration.

## Single tool only

```bash
~/.claude/skills/ai-hooks-integration/scripts/merge_hooks.py \
  --tool claude --path ~/.claude/settings.json \
  --command "python3 $HOME/.claude/skills/pr-monitor/scripts/pr_create_trigger.py"
```

## Verify / debug / remove

```bash
# Debug: log decisions to stderr
echo '{"tool_input":{"command":"gh pr create --fill"},"tool_response":{"success":true}}' \
  | HOOK_DEBUG=1 python3 ~/.claude/skills/pr-monitor/scripts/pr_create_trigger.py

# Remove from all tools
~/.claude/skills/ai-hooks-integration/scripts/remove_all.py --name pr-monitor
```

## Why a hook, not a slash command

The point is zero-friction: the review loop should start itself the instant a PR
exists, without you remembering to invoke it. The hook only *suggests* the skill
via injected context — the agent still decides and you stay in control. If you'd
rather trigger it by hand, just say "monitor my PR" / "babysit this PR" and the
skill's own description handles the rest.
