# Using Manifest with emdash

> How Manifest-configured coding agents run under the emdash desktop app with the
> **full** Manifest configuration (skills, subagents, hooks, MCP, orchestration
> guide, repo guidance) active.

**Last Updated**: 2026-07-12
**Audience**: Manifest users who run agents through emdash
**Related**: [Getting Started](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md)

---

## What emdash is

[emdash](https://github.com/generalaction/emdash) (`generalaction/emdash`, YC W26)
is an open-source Electron **desktop app** — an "Agentic Development Environment"
that runs multiple coding agents **in parallel, each in its own git worktree**. It
does not replace your agent: it **launches your existing agent CLIs** (Claude Code,
Codex, Gemini, Cursor, and ~30 others) as child processes with your **real home
directory** and the working directory set to a normal git worktree checkout.

That launch model is the whole reason emdash needs no Manifest deploy tree:

- **Manifest is a harness for emdash, not a deploy target.** emdash keeps its own
  state in an internal SQLite database and reads **no** file-based config directory
  that Manifest could deploy into. There is deliberately **no `~/.emdash/` config
  directory and no `configs/emdash/` tree** — either would be inert.
- Because the agent runs with your real `HOME` and inside a normal repo checkout,
  it **already inherits the full Manifest configuration transitively**: the
  skills, subagents, hooks, MCP servers, orchestration guide, and settings Manifest
  deploys to `~/.claude/` (and mirrors), plus the repository's committed
  `CLAUDE.md` / `.claude/` / `AGENTS.md`.

"emdash support" is therefore **recognition + verification + gap-closing**, not a
new deployment target.

## Prerequisites

1. **Run the Manifest home deployment first** — run `./bootstrap.sh` so `~/.claude/`
   (skills, subagents, hooks, MCP, orchestration guide, settings) is populated.
   Without it, an emdash session inherits **only** the repository's committed
   config, not the home-deployed skills/subagents/hooks/MCP. (`/env-check`'s
   "emdash Inheritance" section reports this state as `BLOCKED`.)
2. **Install emdash yourself** — `brew install --cask emdash` (macOS) or the
   platform installer from the project. Manifest does **not** install or update it.
3. **Install a Manifest-supported agent** — primarily **Claude Code** (`claude`).
   Codex / Gemini / Cursor also inherit via the same mechanism (best-effort, see
   [Agent scope](#agent-scope-verified-vs-best-effort)).

## Setup

There is **nothing to deploy for emdash itself** — inheritance is automatic because
emdash launches the agent with your real `HOME` inside a normal worktree checkout.

This repository ships a committed **`.emdash.json`** at its root so that fresh
emdash worktrees of Manifest are immediately functional:

- `preservePatterns: ["guidance_local.yml"]` — copies the repo's untracked local
  config into each new worktree.
- `scripts.setup` — runs `git submodule update --init --recursive` (bats helpers)
  and `pip install -r tests/requirements-ci.txt` (matches CI) so `pytest` / `bats`
  run without manual fixup.

Verify inheritance any time:

```bash
# Live probe against your real environment (also runs inside /env-check):
configs/claude/scripts/emdash_inherit_check.sh    # deployed: ~/.claude/scripts/...
# Expect: verdict INHERITED, all dimensions PASS, "manifest hooks preserved".
```

The manual smoke runbook (open the repo in emdash, select Claude Code, confirm each
dimension + a hook firing under ACP mode) lives in
[`specs/483-emdash-support/quickstart.md`](../specs/483-emdash-support/quickstart.md).

## The `.emdash.json` pattern for other repositories

emdash worktrees are fresh checkouts: they **do not** receive a repo's
untracked/ignored files by default and start with no prepared environment. Any repo
can add its own root `.emdash.json` to fix both:

```jsonc
{
  // Untracked/gitignored files copied into every new worktree.
  // Do NOT list tracked files — git already provides them.
  "preservePatterns": ["guidance_local.yml"],
  "scripts": {
    // Runs once when emdash creates the worktree. Idempotent + fail-closed.
    "setup": "git submodule update --init --recursive && pip install -r tests/requirements-ci.txt"
  },
  "shellSetup": ""   // optional per-PTY prelude (e.g. venv activation); keep minimal
}
```

Rules:

- **Never list a secret file in `preservePatterns` unless it is already gitignored.**
  `.env` is the common general-pattern example, but you must **gitignore `.env`
  first** so the provisioning mechanism can never commit it. This repo does **not**
  list `.env` — it neither uses nor gitignores one; its only untracked local config
  is `guidance_local.yml`.
- **Do not list tracked files** (e.g. `.claude/settings.local.json` is tracked in
  this repo — it must not appear).
- Keep `scripts.setup` **idempotent** (a worktree may be re-set-up) and
  **fail-closed** (non-zero exit on failure, so a broken worktree is visible).

## Coexistence caveat: emdash's injected hook

On each session spawn, emdash writes its **own hook wiring** into the agent's
settings file to connect the agent to its callback service. The injected entry is:

```json
{ "type": "command", "command": "curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook" }
```

added as `Stop: [emdashHook, userHook]` — i.e. emdash **appends** its entry
alongside existing ones and tags it with a marker for idempotent dedup. emdash also
adds the settings file's path to `.gitignore`.

What this means for Manifest:

- **Manifest's hooks survive.** Manifest's event hooks live in home
  `~/.claude/settings.json`; the repo's tracked `.claude/settings.local.json` holds
  **permissions** only. emdash's append coexists with both — its idempotent,
  marker-based merge preserves your existing entries. The
  [inheritance probe](#verifying-inheritance) asserts this
  (`manifest_hooks_preserved` / `worktree_permissions_intact`).
- **The injected hook is machine-local — keep it uncommitted.** Because it points
  at a per-session `127.0.0.1` port, it is meaningless on another machine. emdash
  gitignoring the settings path is the intended behavior. If you see an uncommitted
  change to `.claude/settings.local.json` after a session, that is the emdash hook —
  **leave it uncommitted**; do not commit it.
- Manifest adds **no active guard/restore mechanism** and does **not** untrack or
  restructure the settings file. It relies on emdash's merge and documents the
  interaction (this section).

## Agent scope: verified vs best-effort

- **Claude Code is the formally verified agent** — the platform Manifest most fully
  configures and the primary emdash use. Its inheritance is proven by the automated
  launch-environment simulation plus the one-time manual smoke.
- **Codex, Gemini, and Cursor inherit via the same transitive `HOME` + worktree
  mechanism**, on a **best-effort** basis (not formally tested in CI). Where they
  are installed and selected, they read the same home + repo config Claude Code does.
- **Agents emdash can launch that Manifest does not configure are out of the
  guaranteed-parity set.** Such an agent inherits only whatever it natively reads;
  Manifest makes no parity guarantee for it.

## Boundary conditions and known limitations

- **Version basis.** These guarantees target emdash's launch and hook-injection
  behavior as observed in the **current release** (`generalaction/emdash`, YC W26)
  during this feature's development on **2026-07-12**. emdash's launch environment
  and injected-hook shape may change between releases; if a future release writes a
  different shape or scope, re-confirm with the manual smoke and update the
  simulation fixture under `tests/bats/fixtures/emdash/`.
- **Parallel worktrees may race on home-scoped settings.** When emdash injects
  home-scoped hook wiring, multiple concurrent worktree sessions can write the same
  shared `~/.claude/settings.json`. This is **emdash-internal** (last-writer / race
  behavior); Manifest does **not** add a guard for it. The observed idempotent merge
  is designed to preserve unrelated (Manifest) hooks, but the ordering of concurrent
  writes is emdash's responsibility, not Manifest's.
- **emdash worktrees live outside the main checkout.** emdash worktrees are created
  under your emdash worktrees directory (e.g. `~/emdash/worktrees/<project>/...`),
  **outside** the primary repository path. Any Manifest behavior that assumes an
  absolute path under the main checkout — or that the current working directory is
  the main repository — is a **documented limitation** when run from an emdash
  worktree; the inheritance path itself (home `~/.claude/` + the worktree's committed
  config) is unaffected because it does not depend on the main-checkout path.

## Verifying inheritance

| Method | Command | What it proves |
|--------|---------|----------------|
| Live diagnostic | `/env-check` → "emdash Inheritance" section | Home deploy + inheritance status + coexistence caveat (FR-010, SC-005) |
| Direct probe | `configs/claude/scripts/emdash_inherit_check.sh` | Per-dimension report (D1 skills … D6 repo guides) + verdict |
| Automated sim | `bats tests/bats/emdash_inheritance.bats` | Regression protection: reproduces emdash's launch env against fixtures |
| Manual smoke | [`quickstart.md`](../specs/483-emdash-support/quickstart.md) | The real app — including a hook firing under ACP mode |

Probe verdicts: **`INHERITED`** (exit 0, all pass) · **`DEGRADED`** (exit 1, a
dimension failed) · **`BLOCKED`** (exit 2, home deploy missing — run `./bootstrap.sh`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Skills/hooks missing in an emdash session | Home deploy not run (`BLOCKED`) | `./bootstrap.sh`, then re-check with `/env-check` |
| Fresh worktree can't run tests | `.emdash.json` `scripts.setup` didn't run or failed | re-create the worktree; check the emdash task log; verify submodule + `pip` availability |
| Uncommitted change to `.claude/settings.local.json` after a session | emdash's injected `Stop` hook (machine-local) | expected — leave it uncommitted |
| A non-Claude agent behaves differently | Best-effort (not formally verified) | use Claude Code for guaranteed parity |
