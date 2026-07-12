# Phase 0 Research: emdash Support

All spec-level unknowns were resolved during `/speckit-specify` (deep research + on-disk empirical evidence) and `/speckit-clarify` (three decisions). This file records the decisions that drive the design, with rationale and rejected alternatives, plus the plan-phase findings needed to build a faithful verification.

## R1 — emdash's integration model

**Decision**: Treat emdash as an **external harness**, not a Manifest deploy target or parallel-agent provider. Support is **transitive inheritance + verification + gap-closing**.

**Rationale**: emdash (`generalaction/emdash`, YC W26) is an Electron desktop app that spawns the user's real agent CLIs in git worktrees. Empirically verified on this machine:
- App at `/Applications/Emdash.app`; state in SQLite (`~/Library/Application Support/emdash/emdash4.db`); **no `~/.emdash/` config dir**; not on `PATH`, not a brew formula.
- Worktrees are standard git worktrees at `~/emdash/worktrees/<project>/emdash/<branch>` (`.git` → `<repo>/.git/worktrees/...`); committed `.claude/`, `CLAUDE.md`, `AGENTS.md` are present; no marker files injected.
- Agents are launched via a PTY/ACP runtime with the **real `HOME`** (`buildAgentEnv` sets `HOME`/`PATH`), so `~/.claude/` is read normally.

**Alternatives considered**:
- *Mirror the Antigravity pattern* (a `configs/emdash/` tree symlinked to `~/.emdash/`): **rejected** — emdash reads no such directory; the tree would be inert.
- *Register emdash as a parallel-agent provider* (config.py/cli.py): **rejected** — emdash runs agents; it is not an agent invoked by `parallel_agent.py`.

## R2 — Verification method (clarify Q1)

**Decision**: **Hybrid** — (a) an automated bats test that reproduces emdash's launch environment and asserts full config resolution via the shared probe; (b) a documented one-time manual smoke run against the real emdash app. Claude Code is the verified agent.

**Rationale**: emdash is a GUI with no CLI, so driving the real app in CI is impractical and would be flaky (agent auth, ACP session lifecycle). But its launch *conditions* — real `HOME`, worktree cwd, injected `EMDASH_HOOK_*`, and the settings it writes on spawn — are fully reproducible on the filesystem. A deterministic simulation gives regression protection; the manual smoke validates the simulation against reality (and specifically that hooks fire under ACP mode, the one behavior the simulation cannot prove).

**Alternatives**:
- *Automated only*: rejected — never validated against the real app; risk the simulation diverges (esp. ACP hook firing).
- *Manual only*: rejected — no regression protection; future changes silently break inheritance.
- *Drive the real emdash app in CI*: rejected — GUI automation + agent auth is flaky and heavy for a config-inheritance assertion.

## R3 — Hook/settings coexistence (clarify Q2)

**Decision**: **Verify preservation + document.** Trust emdash's idempotent, marker-based merge; the probe/test assert Manifest's hooks survive; `docs/EMDASH.md` documents the `.gitignore`/tracked-file interaction. No guard/restore mechanism; no untracking/restructuring of `.claude/settings.local.json`.

**Rationale (empirical)**: The Emdash bundle shows the injected hook is `{ type: 'command', command: 'curl http://127.0.0.1:$EMDASH_HOOK_PORT/hook' }`, added as `Stop: [emdashHook, userHook]` — i.e. emdash **appends** its entry alongside existing ones and tags them with an `EMDASH_MARKER` for idempotent dedup (`hooks.some(e => JSON.stringify(e).includes(EMDASH_MARKER))`). A documented setting *"When Emdash writes CLI hook configs, also add their paths to .gitignore"* confirms the ignore-rule behavior. So emdash is designed to preserve unrelated (Manifest) hooks; the correct posture is to verify that, not to fight it.

**Key nuance**: This repo's committed `.claude/settings.local.json` holds **permissions** (per `.claude/CLAUDE.md`), while Manifest's event **hooks** are deployed into home `~/.claude/settings.json` (via `merge_settings_hooks`). So emdash's workspace-scoped write coexists with repo *permissions* (no hook collision in the tracked file), and any home-scoped write appends alongside Manifest's home hooks. The tracked-file concern is therefore primarily **git noise** (an uncommitted machine-local hook + a `.gitignore` line), addressed by documentation.

**Ground-truth caveat for implementation**: the exact written shape MUST be confirmed by observing a real emdash spawn (the manual smoke), not by reverse-engineering minified `app.asar`. The simulation fixture encodes the observed shape and is updated if reality differs.

**Alternatives**:
- *Active guard/restore*: rejected — more moving parts, can race emdash's per-spawn writes for no benefit given the merge already preserves.
- *Untrack `.claude/settings.local.json`*: rejected — changes how the repo ships repo-level permissions and diverges from the other platforms' convention.

## R4 — Agent scope (clarify Q3)

**Decision**: Formally verify **Claude Code**; document Codex/Gemini/Cursor as best-effort transitive inheritance (not formally tested).

**Rationale**: Claude Code is Manifest's most-configured agent and the primary emdash use; the transitive mechanism (real `HOME` + worktree) is identical for the others, so a documented statement is honest without a 4× test matrix requiring all CLIs installed/authed in CI.

## R5 — `.emdash.json` content for this repo (US2)

**Decision**: Commit a repo-root `.emdash.json` with:
- `preservePatterns`: untracked local files a worktree needs — `guidance_local.yml` (gitignored; the repo's only untracked local config). **NOT `.env`**: this repo neither uses nor gitignores `.env`, so listing it would risk committing secrets (spec-review F2). (`.claude/settings.local.json` is **tracked**, so it needs no preserve entry.)
- `scripts.setup`: initialize the worktree environment — `git submodule update --init --recursive` (bats helpers per `.gitmodules`) + `pip install -r tests/requirements-ci.txt`. **NOT `uv sync`** (spec-review F1): `.gitignore` documents that this repo uses `pyproject.toml` for tooling config only (ruff/pytest/pyright), not uv dependency management — `uv` is only a graphify runtime; `pyproject.toml` declares no deps, so `uv sync` would fail. CI installs test deps via `pip install -r tests/requirements-ci.txt`; the setup matches CI so `pytest`/`bats` run without manual fixup.
- `shellSetup`: minimal shell prelude if needed (e.g. activate the venv) — kept empty/minimal unless setup requires it.

**Rationale**: emdash worktrees are fresh checkouts missing untracked files and a prepared environment; `.emdash.json` (`preservePatterns` + `scripts`) is emdash's supported mechanism to fix both. Exact commands pinned during implementation against the repo's actual bootstrap/test entry points.

**Alternatives**: *Rely on the user to set up each worktree manually*: rejected — fails US2/SC-002 (a fresh worktree should pass verification with no manual fixup).

## R6 — Shared probe as the single source of truth (design choice)

**Decision**: One script `configs/claude/scripts/emdash_inherit_check.sh` computes the inheritance report; **env-check calls it live** (real `HOME`) and the **bats test calls it against a fixture**. Contract in `contracts/inheritance-probe.md`.

**Rationale**: DRY — FR-010 (diagnostic) and FR-011a (automated verification) assert the same thing; a shared probe prevents drift between the live check and the test. Fails closed (non-zero exit) and routes messages through `err()` per repo conventions.

**Alternatives**: *Separate logic in env-check and the test*: rejected — guaranteed drift; two places to update when a new inheritance dimension is added.

## Open items deferred to `/speckit-tasks` / implementation
- Exact `scripts.setup` command string for `.emdash.json` (pin to the repo's real env-setup entry point).
- Exact bats fixture bytes for the emdash-merged settings (encode observed shape from the manual smoke).
- Whether env-check's emdash section is gated by an emdash-detected condition (present `/Applications/Emdash.app` or `~/emdash/`) — default: Info-level, always shown, detail conditional on detection.
