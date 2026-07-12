# Quickstart: Using Manifest with emdash

Audience: a Manifest user who wants to run Manifest-configured coding agents through the emdash desktop app with the **full** Manifest configuration (skills, subagents, hooks, MCP, orchestration guide) active. This is also the manual smoke runbook for FR-011b.

## Prerequisites

1. **Manifest home deployment done** — run `./bootstrap.sh` so `~/.claude/` (skills, subagents, hooks, MCP, orchestration guide, settings) is populated. Without this, emdash sessions inherit only the repo's committed config. (Edge case: "home deployment not run".)
2. **emdash installed** — `brew install --cask emdash` (macOS) or the platform installer from emdash.ai. Manifest does not install emdash.
3. **A Manifest-supported agent installed** — primarily **Claude Code** (`claude`); Codex/Gemini/Cursor also inherit via the same mechanism (best-effort).

## Setup (per machine)

- Nothing to deploy for emdash itself — inheritance is automatic because emdash launches the agent with your real `HOME` inside a normal worktree checkout.
- This repository ships a committed `.emdash.json` so its emdash worktrees are functional (preserves `guidance_local.yml`/`.env`, runs submodule + Python env setup). Other repos can add their own `.emdash.json` following the same pattern (`docs/EMDASH.md`).

## Verify inheritance (automated)

```bash
# Live check against your real environment (also runs inside /env-check):
configs/claude/scripts/emdash_inherit_check.sh
# Expect: verdict INHERITED, all dimensions PASS, "manifest hooks preserved".

# Or via the skill:
/env-check          # the "emdash Inheritance" section reports the same
```

## Verify inheritance (manual smoke — the real app)

1. Open this repository in emdash and start a task (creates a worktree under `~/emdash/worktrees/Manifest/emdash/<branch>`).
2. Select **Claude Code** as the agent.
3. In the emdash agent session, confirm each inheritance dimension — matching a terminal session in the repo:
   - **Skills**: invoke a known Manifest skill (e.g. `/help` or `/env-check`) → it resolves.
   - **Subagents**: ask the agent to dispatch a Manifest subagent (e.g. Explore) → it is available.
   - **Hooks**: trigger an action a Manifest hook intercepts → the hook fires (this is the one behavior only the real app proves, since it exercises ACP mode).
   - **MCP**: confirm a configured MCP tool is listed/usable.
   - **Guides**: confirm `CLAUDE.md`/`AGENTS.md` guidance is in effect.
4. **Coexistence check**: after the session spawns, inspect the worktree's `.claude/settings.local.json` — emdash appends its own `Stop` hook (`curl …$EMDASH_HOOK_PORT/hook`). Confirm Manifest's committed permissions/hooks are intact. This machine-local hook is expected to be uncommitted/gitignored — do not commit it (see `docs/EMDASH.md`).

## Expected outcome (Success Criteria)

- SC-001/SC-003: every skill/subagent/hook/MCP active in a terminal Claude Code session is active in the emdash session; Manifest hooks survive emdash's write.
- SC-002: a fresh emdash worktree passes `bats tests/bats/` and `pytest tests/python/` with no manual environment fixup.
- SC-005: `/env-check` reports emdash presence + inheritance status.
- SC-006: no `~/.emdash/` config dir and no `configs/emdash/` tree were created.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Skills/hooks missing in emdash session | Home deploy not run | `./bootstrap.sh`, then re-check |
| Fresh worktree can't run tests | `.emdash.json` `scripts.setup` didn't run or failed | re-create worktree; check emdash task log; verify submodule/uv availability |
| Uncommitted change to `.claude/settings.local.json` after a session | emdash's injected `Stop` hook | expected; leave uncommitted (machine-local) — see `docs/EMDASH.md` |
| A non-Claude agent behaves differently | Best-effort (not formally verified) | use Claude Code for guaranteed parity, or follow `docs/EMDASH.md` |
