# manifest uv CLI Design

**Date:** 2026-07-13
**Status:** Approved (brainstorming)
**Scope:** Home-deployed Python runtime (`~/.claude/scripts/`) — isolated execution via uv,
unified `manifest` CLI, one-release deprecation shims for legacy `.py` entry points.

**Out of scope:** Repo CI/pytest workflow, emdash `.emdash.json` setup, inline `python3 -c`
snippets in bash hooks (stdlib-only helpers remain unchanged).

---

## Problem

Manifest's home-deployed Python tools (`parallel_agent.py`, `smoke_test.py`, `cddl_loop.py`,
skillclaw tools, etc.) run against whatever `python3` is on PATH. Bootstrap installs runtime
deps with `pip install --user`, which causes:

1. **Missing packages** — bootstrap skipped, partial install, or wrong Python selected →
   `ModuleNotFoundError` at skill/hook runtime.
2. **Host Python pollution** — `--user` installs compete with system Python and other projects.
3. **Version drift** — `configs/claude/scripts/requirements.txt`, smoke opt-in requirement
   files, and bootstrap pins can diverge; no single lockfile governs the deployed runtime.

Coding standards already say "keep environments isolated (venv/uv)" but nothing enforces it
for the deployed home tree.

---

## Goals

1. Every home-runtime Python invocation uses a **dedicated uv-managed venv** at
   `~/.claude/.venv` with a **committed `uv.lock`**.
2. Introduce a **unified `manifest` CLI** as the canonical invocation surface.
3. Keep **legacy script paths working for one release** via deprecation shims, then remove.
4. **Fail closed** when the venv or `uv` is missing — clear message to re-run bootstrap.
5. Match existing deploy patterns (`sync-skills` → `~/.local/bin`).

---

## Non-Goals

- Migrating repo-root dev/CI (`tests/requirements-ci.txt`, root `pyproject.toml` for ruff/pytest).
- Replacing bash-first tools (`sync-skills`, `git_ops.sh`, `lifecycle.sh`).
- Packaging every deployed `.py` file (generators like `generate_commands_doc.py` stay
  repo-dev tools; not exposed as `manifest` subcommands in v1).
- `uv tool install manifest` as a globally versioned artifact separate from the deploy tree.

---

## Architecture

```text
bootstrap.sh
    ├─► ensure_uv()                    (existing; graphify prerequisite)
    ├─► deploy_configs → ~/.claude/    (includes pyproject.toml + uv.lock + scripts/)
    └─► uv_sync_home_runtime()         (NEW: replaces pip install --user)
            ├─► uv sync --project "$HOME/.claude"
            ├─► creates/updates ~/.claude/.venv
            └─► symlinks ~/.local/bin/manifest → ~/.claude/.venv/bin/manifest

Invocation (canonical):
    manifest parallel-agent --json --review /abs/path/file
    manifest smoke run --catalog smoke-catalog/manifest.yaml
    manifest cddl start specs/123-feature

Invocation (deprecated, one release):
    ~/.claude/scripts/parallel_agent.py …   → shim → manifest parallel-agent …
```

### Deployed layout

```text
~/.claude/
├── pyproject.toml          # runtime project + [project.scripts]
├── uv.lock                 # pinned resolution (committed in repo at configs/claude/)
├── .venv/                  # created by uv; never committed
└── scripts/
    ├── manifest_cli/       # NEW: top-level router (click)
    ├── agents/             # unchanged
    ├── smoke_orchestrator/ # unchanged
    ├── cddl/               # unchanged
    ├── parallel_agent.py   # deprecation shim (removed N+1)
    ├── smoke_test.py       # deprecation shim
    ├── cddl_loop.py        # deprecation shim
    └── skillclaw_*.py      # deprecation shims
```

**Source of truth in repo:** `configs/claude/pyproject.toml` + `configs/claude/uv.lock`,
deployed to `~/.claude/` alongside `configs/claude/scripts/`.

Root `pyproject.toml` remains **dev-only** (ruff, pytest, pyright). Two projects, two concerns.

---

## Dependency model

### Consolidation

| Today | After |
|-------|-------|
| `configs/claude/scripts/requirements.txt` | `[project.dependencies]` in `configs/claude/pyproject.toml` |
| `tests/requirements-smoke.txt` (playwright, pyyaml) | `[dependency-groups] smoke` |
| `tests/requirements-smoke-agent.txt` (browser-use) | `[dependency-groups] smoke-agent` |

Default `uv sync` installs **core** runtime deps (parallel agent, cddl, skillclaw, shared libs).
Smoke deps install when smoke is enabled at bootstrap time:

```bash
uv sync --project "$HOME/.claude" --group smoke          # --enable-smoke
uv sync --project "$HOME/.claude" --group smoke-agent    # --enable-browser-use (implies smoke)
```

Pins are recorded in `uv.lock`. Bootstrap and re-bootstrap always converge the venv to the
lockfile — eliminating drift between docs, bootstrap, and runtime.

### pyproject sketch

```toml
[project]
name = "manifest-runtime"
version = "0.0.0"  # not published; tracks deploy tree
requires-python = ">=3.11"
dependencies = [
  # migrated from configs/claude/scripts/requirements.txt
  "anthropic>=0.40.0",
  "google-genai>=1.0.0",
  "aiohttp>=3.9.0",
  # …
]

[project.scripts]
manifest = "manifest_cli:main"

[dependency-groups]
smoke = ["playwright==1.60.0", "pyyaml==6.0.3"]
smoke-agent = ["browser-use>=0.13.0"]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Package discovery includes `scripts/` packages (`agents`, `smoke_orchestrator`, `cddl`) and
`scripts/manifest_cli/` via explicit `packages` or `tool.hatch.build.targets.wheel` config.

---

## `manifest` CLI

### Router

- **Library:** `click` (already a parallel-agent dependency).
- **Module:** `scripts/manifest_cli/__init__.py` with `main()` entry point.
- **`manifest --help`** lists subcommands; each subcommand delegates to the existing package
  `main()` — no flag rewiring in v1.

### Subcommands (v1)

| Subcommand | Replaces | Delegates to |
|------------|----------|--------------|
| `parallel-agent` | `parallel_agent.py` | `agents.cli:main` (async wrapper) |
| `smoke` | `smoke_test.py` | `smoke_orchestrator.cli:main` |
| `cddl` | `cddl_loop.py` | `cddl.cli:main` (preserves exit-code contract) |
| `skillclaw ingest` | `skillclaw_ingest.py` | existing `main()` |
| `skillclaw evolve` | `skillclaw_evolve.py` | existing `main()` |
| `skillclaw promote` | `skillclaw_promote.py` | existing `main()` |
| `skillclaw audit` | `skillclaw_audit.py` | existing `main()` |
| `skillclaw scrub` | `skillclaw_scrub.py` | existing `main()` |
| `doctor` | (new) | env sanity: uv, venv, import smoke test |

**Not in v1:** `generate-*`, `command-catalog`, `guidance-hint`, `budget-broker`, `reconcile`
(generators and bash-delegated tools stay as-is or gain subcommands later).

### Exit codes

Subcommands **preserve existing exit codes** (especially `cddl` 0/2/3/4/5/6/7). The router
never swallows `SystemExit` codes.

---

## Bootstrap & deploy changes

### Replace `install_python_dependencies()`

Remove `pip install --user -r requirements.txt`. New `uv_sync_home_runtime()`:

1. Resolve `uv` (`command -v uv` or `$HOME/.local/bin/uv`).
2. Fail with actionable message if `uv` missing (bootstrap should have installed it).
3. Run `uv sync --project "$TARGET_DIR"` (where `TARGET_DIR` is `~/.claude`).
4. If `--enable-smoke`: add `--group smoke` (+ `--group smoke-agent` when browser-use enabled).
5. Symlink `$TARGET_DIR/.venv/bin/manifest` → `$HOME/.local/bin/manifest` (same pattern as
   `deploy_sync_skills`).
6. Ensure `$HOME/.local/bin` on PATH (reuse existing profile logic).

`uv sync` is **idempotent** and safe on re-bootstrap.

### Deploy manifest

Extend `deploy_configs` (or `deploy_sync_skills` sibling `deploy_manifest_cli`) to:

- Copy `configs/claude/pyproject.toml` and `configs/claude/uv.lock` to `~/.claude/`.
- Run `uv_sync_home_runtime` after file deploy.

### Retire `requirements.txt`

Delete `configs/claude/scripts/requirements.txt` after migration (symlinked platform copies
follow). Document in bootstrap output: "Runtime deps: uv.lock @ ~/.claude".

---

## Deprecation shims (one release)

Each legacy `*.py` entry point becomes a thin shim:

1. Print **once per invocation** to stderr:
   `parallel_agent.py is deprecated; use: manifest parallel-agent`
2. Re-exec via venv: `"$HOME/.claude/.venv/bin/python" -m manifest_cli parallel-agent "$@"`
   or delegate in-process after `sys.path` setup.
3. **Preserve argv forwarding** byte-for-byte (skills embed exact flag sequences).

**Shell wrappers** (`spec_review.sh`, `verification_gate.sh`, `skillclaw_promote.sh`,
`deploy_reconcile.sh`) update to call `manifest …` directly in the **same release** (not via
shims) so dogfooding starts immediately.

**Release N+1:** remove shims; a missing shim is acceptable because docs/skills/hooks will
have migrated. Optional hard-fail stub: "removed; use manifest …".

---

## Error handling

| Condition | Behavior |
|-----------|----------|
| `~/.claude/.venv` missing | stderr: `manifest: home runtime not installed — re-run ./bootstrap.sh`; exit 1 |
| `uv` missing | stderr: `manifest: uv not found — re-run ./bootstrap.sh --enable-graphify` (or install uv); exit 1 |
| `uv sync` failed during bootstrap | bootstrap **warns** for parallel-agent (today's behavior) but `env-check` reports **BLOCKED** |
| Import error inside subcommand | propagate; do not fall back to system Python |
| Smoke group not installed | `manifest smoke` stderr: `smoke deps not installed — re-run ./bootstrap.sh --enable-smoke`; exit 1 |

**No fail-open to system `python3`.** The whole point is to stop silent wrong-environment execution.

---

## `env-check` integration

Add a **Home Python Runtime** section:

- `uv` on PATH
- `~/.claude/.venv` exists
- `manifest` on PATH
- `manifest doctor` passes (imports `anthropic`, `yaml`, etc.)
- Optional: smoke group present when `services.yml` has smoke enabled

Verdict: **BLOCKED** if any hard check fails (same severity as missing `~/.claude/skills`).

---

## Testing

| Layer | What |
|-------|------|
| bats | `uv_sync_home_runtime` idempotency in SANDBOX with fake HOME |
| pytest | `manifest_cli` router: subcommand dispatch, argv passthrough, exit codes |
| pytest | shim prints deprecation, forwards to same exit code as canonical |
| CI | `uv lock --check` job: lockfile matches pyproject |
| smoke-catalog | Update Lite-tier entry to invoke `manifest parallel-agent` (or `manifest smoke`) |

Repo CI **does not** switch to uv for pytest in v1; tests mock/stub `MANIFEST_HOME` and venv
paths where integration tests need them.

---

## Migration checklist (implementation)

1. Add `configs/claude/pyproject.toml` + generate `uv.lock`.
2. Add `manifest_cli` router + `manifest doctor`.
3. Convert entry-point `.py` files to shims.
4. Replace `install_python_dependencies` with `uv_sync_home_runtime`.
5. Deploy pyproject/lock; symlink `manifest` to `~/.local/bin`.
6. Update shell wrappers and high-traffic docs (`CLAUDE.md`, orchestration rules, skills referencing
   `parallel_agent.py`) to `manifest …`.
7. Extend `env-check`.
8. Remove `requirements.txt`; add `uv lock --check` CI step.
9. Release N+1: delete shims.

---

## Open decisions (resolved)

| Question | Decision |
|----------|----------|
| uv vs venv | **uv only** (`uv sync` + `uv.lock`) |
| Invocation | **Unified `manifest` CLI**; shims one release |
| Scope | **Home-deployed scripts only** |
| pyproject location | **`configs/claude/`** deployed to `~/.claude/` |
| Package manager for runtime | **uv**; retire `pip install --user` for runtime deps |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| uv not installed on minimal hosts | Reuse existing `ensure_uv()`; fail-closed `env-check` |
| Slower first invoke | `uv sync` at bootstrap, not per invoke; venv bin is direct |
| Large lockfile churn | `uv lock --check` in CI; dependabot-style manual refresh |
| Click + asyncio (parallel-agent) | Router uses `asyncio.run()` only for async subcommands |
| Python 3.14 / greenlet (smoke) | Keep existing playwright pin in smoke group |
