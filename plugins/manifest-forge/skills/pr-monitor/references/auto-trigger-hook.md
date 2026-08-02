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

## Install through the active harness coordinator

The bundle does not guess a harness home or edit another plugin. Ask the active
harness coordinator to install an ownership-marked lifecycle hook named
`manifest-forge:pr-monitor`. The handler command must invoke
`scripts/pr_create_trigger.py` relative to this skill directory, with an argv
array equivalent to:

```text
["python3", "<installed-pr-monitor-skill>/scripts/pr_create_trigger.py"]
```

The coordinator resolves `<installed-pr-monitor-skill>`, chooses the native
event for the active harness, records bundle ownership, and performs an atomic
merge into that harness's configuration. The handler filters successful
`gh pr create` / `glab mr create` commands itself, so no shell interpolation or
credential lookup belongs in the hook declaration.

Codex and Antigravity have no event-hook substrate. On those harnesses the
coordinator reports the capability as degraded and the operator runs
`/pr-monitor` manually after opening a PR.

## Verify / debug / remove

```bash
# Debug: log decisions to stderr
echo '{"tool_input":{"command":"gh pr create --fill"},"tool_response":{"success":true}}' \
  | HOOK_DEBUG=1 python3 scripts/pr_create_trigger.py

# Remove by asking the active coordinator to remove ownership marker
# manifest-forge:pr-monitor.
```

## Why a hook, not a slash command

The point is zero-friction: the review loop should start itself the instant a PR
exists, without you remembering to invoke it. The hook only *suggests* the skill
via injected context — the agent still decides and you stay in control. If you'd
rather trigger it by hand, just say "monitor my PR" / "babysit this PR" and the
skill's own description handles the rest.
