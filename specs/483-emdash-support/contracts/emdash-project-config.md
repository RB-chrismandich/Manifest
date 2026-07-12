# Contract: `.emdash.json` Project Configuration

**Interface**: the repository's contract with the emdash desktop app. emdash reads this file at the repo root when creating worktrees for the project. This feature commits it (FR-006, US2).

## Schema (subset Manifest uses)

```jsonc
{
  // Untracked/gitignored files copied into every new worktree.
  // Tracked files are already present via git — do NOT list them here.
  // This repo's only untracked local config is guidance_local.yml (gitignored).
  // NOT .env: this repo has none and .env is not gitignored here — listing it
  // would risk committing secrets. (.env is the general-pattern example in docs.)
  "preservePatterns": ["guidance_local.yml"],

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
3. **Secrets stay untracked** — any preserved file that holds secrets MUST already be gitignored; the repo never commits them (FR-006 AC3). For THIS repo, `preservePatterns` is `guidance_local.yml` (gitignored). `.env` is the general-pattern example only; it is NOT listed here because this repo neither uses nor gitignores it — other repos adding `.env` MUST gitignore it first (documented in `docs/EMDASH.md`).
4. **`scripts.setup` idempotent + fail-closed** — safe to re-run; non-zero exit on failure so a broken worktree is visible, not silently degraded.
5. **Exact commands finalized in implementation** against the repo's real submodule + Python-env entry points; the values above are the design intent.

## Verified by

- `.emdash.json` JSON-validity check (CI, alongside the existing `yaml.safe_load` config checks).
- Manual smoke (`quickstart.md`): create a fresh emdash worktree → confirm preserved files present and `scripts.setup` produced a worktree where `pytest`/`bats` run (SC-002).
