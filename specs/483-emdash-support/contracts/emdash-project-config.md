# Contract: `.emdash.json` Project Configuration

**Interface**: the repository's contract with the emdash desktop app. emdash reads this file at the repo root when creating worktrees for the project. This feature commits it (FR-006, US2).

## Schema (subset Manifest uses)

```jsonc
{
  // Untracked/gitignored files WITHIN THE REPO TREE copied into every new
  // worktree. Tracked files are already present via git — do NOT list them
  // here. This repo currently has none: `guidance_local.yml` is gitignored
  // but lives at `~/.claude/config/guidance_local.yml` (HOME-side, outside
  // the repo tree entirely), so it could never match a preservePatterns glob
  // regardless of what's listed here — do NOT list it.
  // NOT .env either: this repo has none and .env is not gitignored here —
  // listing it would risk committing secrets. (.env is the general-pattern
  // example in docs, for repos that DO have an in-tree untracked file.)
  "preservePatterns": [],

  "scripts": {
    // Runs once when emdash creates the worktree. Must be idempotent + fail closed.
    // pip (matching CI), NOT `uv sync`: this repo uses pyproject.toml for tooling
    // config only (ruff/pytest/pyright), not uv dependency management (see .gitignore).
    "setup": "git submodule update --init --recursive && pip install -r tests/requirements-ci.txt",
    // Optional; omitted by Manifest (no single run target).
    "run": null,
    // Optional; omitted.
    "teardown": null
  },

  // Optional shell prelude run in each PTY before the interactive shell.
  // Kept minimal/empty unless env activation is required.
  "shellSetup": ""
}
```

## Rules

1. **Valid JSON** — CI asserts `python3 -c "import json; json.load(open('.emdash.json'))"`.
2. **No tracked files in `preservePatterns`** — `.claude/settings.local.json` is tracked; it MUST NOT appear here.
3. **Secrets stay untracked** — any preserved file that holds secrets MUST already be gitignored; the repo never commits them (FR-006 AC3). For THIS repo, `preservePatterns` is `[]` (empty): its only gitignored config-like name, `guidance_local.yml`, resolves to `~/.claude/config/guidance_local.yml` (HOME-side), never a path inside the repo/worktree tree, so it is not a valid preserve target and is not listed. `.env` is the general-pattern example only; it is NOT listed here because this repo neither uses nor gitignores it — other repos adding an in-tree untracked file (e.g. `.env`) MUST gitignore it first (documented in `docs/EMDASH.md`).
4. **`scripts.setup` idempotent + fail-closed** — safe to re-run; non-zero exit on failure so a broken worktree is visible, not silently degraded.
5. **Exact commands finalized in implementation** against the repo's real submodule + Python-env entry points; the values above are the design intent.

## Verified by

- `.emdash.json` JSON-validity check (CI, alongside the existing `yaml.safe_load` config checks).
- Manual smoke (`quickstart.md`): create a fresh emdash worktree → confirm preserved files present and `scripts.setup` produced a worktree where `pytest`/`bats` run (SC-002).
