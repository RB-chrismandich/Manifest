# Quickstart: Command Discovery & Workflow Guidance

**Feature**: 362-command-help-hints | **Date**: 2026-06-21

How the feature is used once implemented. Doubles as the acceptance walkthrough for SC-001
and SC-005 (trace the hint chain end-to-end).

## 1. Discover a command (US1 / SC-001)

```text
/help                         # full listing, grouped by category
/help branches                # intent search → e.g. branch-clean, repo-hygiene
/help --category security     # everything in the security category
```

Each row: `` `/name` — one-line description _(when to use)_ ``. Unavailable commands are
marked with a reason (e.g. *unavailable: service disabled*) and never recommended first.

**Pass check**: a stated task ("clean up branches") surfaces the right command within the
first screen, and the listing matches the installed skill set exactly.

## 2. Browse the generated reference (US1)

```bash
# docs/COMMANDS.md is generated from the skill source of truth
$EDITOR docs/COMMANDS.md
```

Regenerate / verify it is in sync:

```bash
configs/claude/scripts/generate_commands_doc.py          # regenerate
configs/claude/scripts/generate_commands_doc.py --check   # exit 1 if drift (CI gate)
```

**Pass check** (SC-002): add a skill → `--check` fails until regenerated → after regen, doc matches.

## 3. Receive a workflow hint (US2 / SC-003)

Trigger a recognized moment and see a one-shot hint:

```bash
git commit -m "wip"      # → "Before committing: /verify to lint+test, or /project-commit …"
gh pr create ...         # → PR-related guidance
```

Unrelated actions produce no hint. Hints are transient output — they are not added to the
always-loaded context (FR-009).

## 4. Tune or silence guidance (US3 / SC-004)

```yaml
# configs/claude/config/guidance.yml
enabled: true
categories: { hints: true, reminders: false, discovery: true }   # silence reminders only
verbosity: quiet
```

```bash
# global kill-switch
# set enabled: false → zero hints/reminders thereafter
```

**Pass check**: disable reminders → reminders stop, hints continue; set `enabled: false` → all stop.

## 5. End-to-end guidance chain (SC-005)

From a fresh session, complete `verify → commit → open PR` using only surfaced guidance:

1. Start a change → `/help` (or a hint) points to `/verify`.
2. Run `/verify` → on success, commit; the pre-commit moment surfaces `/project-commit`.
3. After commit, the PR-open moment surfaces the PR command.

**Pass check**: each step's next command is reachable from the previous step's guidance —
no external docs needed.

## 6. Cross-platform parity (FR-011)

The same catalog drives all five agents:
- **Claude Code**: `/help` skill + hooks.
- **Cursor**: generated `.mdc` rule (via `generate_cursor_rules.sh`) + `docs/COMMANDS.md`.
- **Gemini / Codex**: generated catalog table injected into `GEMINI.md` / `AGENTS.md` (budget-bounded).
- **Antigravity**: via existing symlinks to `../claude`.

## Verify the feature (developer)

```bash
pytest tests/python/command_help/ -q
npx bats tests/bats/command_help_cli.bats tests/bats/commands_doc_drift.bats tests/bats/guidance_hint_hook.bats
```
