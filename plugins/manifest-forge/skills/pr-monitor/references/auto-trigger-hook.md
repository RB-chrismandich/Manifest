# Auto-trigger hook: run the monitor when a PR is created

This skill can fire automatically the moment you open a PR/MR from an AI coding
tool. The trigger is a **tool-lifecycle hook** (Claude Code PostToolUse and the
equivalents in Cursor and Gemini CLI) that watches shell commands for a
successful `gh pr create` / `glab mr create` and then nudges the agent to run
`pr-monitor` on the new PR. Codex and Antigravity have no event-hook substrate
(spec 362, FR-011), so on those tools you run the skill by hand instead — see
"Why a hook, not a slash command" below.

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

## Install across all three hook-capable tools (recommended)

Use the `ai-hooks-integration` skill's unified installer — no path to supply,
since skill storage has moved three times already (bootstrap copy ->
apm-managed `~/.manifest/skills` -> plugin bundles, PR #685) and every
hand-written `~/.claude/skills/...` path in this doc has gone stale at least
once as a result. Locate the installer via the plugin cache or a repo
checkout (`find ~/.claude/plugins/cache -path '*/manifest-workspace/*' -name
install_all.py`, or `plugins/manifest-workspace/skills/ai-hooks-integration/scripts/install_all.py`
in a Manifest checkout) and run it with the built-in default handler — no
`--handler` needed for pr-monitor, it's the installer's default:

```bash
install_all.py --unified --name pr-monitor --dry-run   # drop --dry-run to apply
```

This writes `~/.claude/scripts/hook_dispatch.py --source <tool>` into each
config instead of an absolute path to `unified_hook.py`/`pr_create_trigger.py`.
`hook_dispatch.py` lives at `~/.claude/scripts/` — deployed by `bootstrap.sh`,
untouched by skill/plugin churn — and resolves the real script locations at
fire-time, so the installed command never goes stale again even if skill
storage moves a fourth time.

Unified mode registers the handler on each tool's tool-lifecycle event and
normalizes the payload; the handler (`pr_create_trigger.py`) does its own
filtering — it only acts on a successful `gh pr create` / `glab mr create` and
no-ops on everything else, so there's no per-event/matcher flag to set.

This registers the equivalent event per tool:

| Tool        | Config                     | Event               |
|-------------|----------------------------|----------------------|
| Claude Code | `~/.claude/settings.json`  | PostToolUse (Bash)   |
| Gemini CLI  | `~/.gemini/settings.json`  | AfterTool            |
| Cursor      | `~/.cursor/hooks.json`     | afterShellExecution  |

Codex and Antigravity have no event-hook substrate — `configs/antigravity/`
symlinks only config/skills/.plans, not a `settings.json` for hooks to live in
— so neither tool can auto-trigger this skill; run `/pr-monitor` by hand after
opening a PR from either one (see AGENTS.md's Workflow Reminders). OpenCode, if
used, takes a plugin instead — see `install_opencode_plugin.py` in
ai-hooks-integration.

## Single tool only

Prefer the unified installer above — it's what wires in `hook_dispatch.py`'s
stale-path protection. `merge_hooks.py --command` is the raw lower-level
primitive it calls and takes whatever command string you give it verbatim, so
pointing it straight at a script path reintroduces the staleness problem this
doc exists to warn about.

## Verify / debug / remove

```bash
# Debug: log decisions to stderr (once installed, run the live command with
# HOOK_DEBUG=1 rather than invoking pr_create_trigger.py by a hand-typed path)
echo '{"tool_input":{"command":"gh pr create --fill"},"tool_response":{"success":true}}' \
  | HOOK_DEBUG=1 ~/.claude/scripts/hook_dispatch.py --source claude

# Remove from all tools (same directory as install_all.py — see "Install
# across all three hook-capable tools" above for how to locate it)
remove_all.py --name pr-monitor
```

## Why a hook, not a slash command

The point is zero-friction: the review loop should start itself the instant a PR
exists, without you remembering to invoke it. The hook only *suggests* the skill
via injected context — the agent still decides and you stay in control. If you'd
rather trigger it by hand, just say "monitor my PR" / "babysit this PR" and the
skill's own description handles the rest.
