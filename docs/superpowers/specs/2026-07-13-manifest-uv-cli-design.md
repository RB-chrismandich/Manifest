# manifest uv CLI Design

**Date:** 2026-07-13
**Status:** Approved (brainstorming)
**Scope:** Home-deployed Python runtime (`~/.claude/scripts/`) — isolated execution via uv,
unified `manifest` CLI, one-release deprecation shims for legacy `.py` entry points.

**Out of scope:** emdash `.emdash.json` setup, inline `python3 -c` snippets in bash hooks
(stdlib-only helpers remain unchanged).

**In scope (CI exceptions):** repo CI may gain **additive** steps (`uv lock --check`,
`uv build`, requirements drift test, `tests/requirements-runtime.txt` install) while the
main pytest runner stays on `pip` + `tests/requirements-ci.txt` (not full `uv sync` for CI).

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
    ├─► check_uv() unconditionally     (existing install.sh helper; required for runtime + graphify)
    ├─► deploy_configs → ~/.claude/    (includes pyproject.toml + uv.lock + scripts/)
    └─► uv_sync_home_runtime()         (NEW: replaces pip install --user)
            ├─► uv sync --project "$HOME/.claude"
            ├─► creates/updates ~/.claude/.venv
            └─► deploys ~/.local/bin/manifest wrapper (NOT a symlink into .venv)

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
├── config/
│   └── services.yml        # deployed by existing deploy_configs (group selection source)
└── scripts/
    ├── manifest_cli/       # NEW: top-level router (click) + __main__.py
    ├── agents/             # unchanged
    ├── smoke_orchestrator/ # unchanged
    ├── cddl/               # unchanged
    ├── skillclaw/          # NEW: implementations moved from skillclaw_*.py
    ├── parallel_agent.py   # deprecation shim (removed N+1)
    ├── smoke_test.py       # deprecation shim
    ├── cddl_loop.py        # deprecation shim
    └── skillclaw_*.py      # pure disposable shims (no logic)
    └── reconcile_core.py   # v1: invoked by deploy_reconcile.sh via venv python
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
| `tests/requirements-smoke.txt` (playwright) | `[dependency-groups] smoke` |
| `tests/requirements-smoke-agent.txt` (browser-use) | `[dependency-groups] smoke-agent` |

**CI coexistence (v1):** `tests/requirements-smoke*.txt` **remain** for repo CI/pytest
(non-goal: CI does not switch to uv yet). Pins must match `configs/claude/pyproject.toml`
groups; add a drift test or comment header `sync-with: configs/claude/uv.lock`.

**Dev/CI core runtime deps:** add `tests/requirements-runtime.txt` (core parallel-agent /
cddl deps exported from `configs/claude/pyproject.toml`) for pytest jobs that import
`configs/claude/scripts/` packages. CI installs it alongside `tests/requirements-ci.txt`.
Home bootstrap does **not** use this file — it uses `uv.lock`.

Default `uv sync` installs **core** runtime deps (parallel agent, cddl, skillclaw, shared libs).
Smoke deps install when smoke is enabled at bootstrap time:

```bash
uv sync --project "$HOME/.claude" --group smoke          # --enable-smoke
uv sync --project "$HOME/.claude" --group smoke --group smoke-agent   # --enable-browser-use (implies smoke)
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
  "pyyaml>=6.0.1",   # core: parallel-agent, cddl, env-check/doctor (not smoke-only)
  # …
]

[project.scripts]
manifest = "manifest_cli:main"

[dependency-groups]
smoke = ["playwright==1.60.0"]   # pyyaml is core; playwright is smoke-only
# smoke-agent is additive; bootstrap always passes --group smoke --group smoke-agent together.
smoke-agent = ["browser-use>=0.13.0"]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# Hatch: packages live under scripts/ on disk; sources remaps to top-level imports.
# Verify in CI with `uv build --project configs/claude` before merge.
[tool.hatch.build.targets.wheel]
packages = [
  "scripts/agents",
  "scripts/smoke_orchestrator",
  "scripts/skillclaw",
  "scripts/manifest_cli",
]

[tool.hatch.build.targets.wheel.sources]
"scripts/agents" = "agents"
"scripts/smoke_orchestrator" = "smoke_orchestrator"
"scripts/skillclaw" = "skillclaw"
"scripts/manifest_cli" = "manifest_cli"
```

Entry point `manifest = "manifest_cli:main"` resolves because `scripts/manifest_cli`
is installed as importable `manifest_cli` (not `scripts.manifest_cli`).

**skillclaw refactor (required before shims):** move implementation from top-level
`skillclaw_*.py` into `scripts/skillclaw/` (`ingest.py`, `evolve.py`, etc. with existing
`main()` functions). Legacy `skillclaw_*.py` files become **pure shims only** — they must not
retain logic, or v1 shims would circularly delegate and N+1 removal would delete the feature.

---

## `manifest` CLI

### Router

- **Library:** `click` (already a parallel-agent dependency).
- **Module:** `scripts/manifest_cli/__init__.py` with `main()` entry point.
- **`manifest --help`** lists subcommands; each subcommand delegates to the existing package
  `main()` — no flag rewiring in v1.
- **Async:** only `parallel-agent` wraps `agents.cli.main` with `asyncio.run()` at the
  Click subcommand layer. `agents.cli.main` is **not** called from a context that already
  has a running loop (avoids nested `asyncio.run()`).

### Subcommands (v1)

| Subcommand | Replaces | Delegates to |
|------------|----------|--------------|
| `parallel-agent` | `parallel_agent.py` | `agents.cli:main` (async wrapper) |
| `smoke` | `smoke_test.py` | `smoke_orchestrator.cli:main` |
| `skillclaw ingest` | `skillclaw_ingest.py` | `skillclaw.ingest:main` |
| `skillclaw evolve` | `skillclaw_evolve.py` | `skillclaw.evolve:main` |
| `skillclaw promote` | `skillclaw_promote.py` | `skillclaw.promote:main` |
| `skillclaw audit` | `skillclaw_audit.py` | `skillclaw.audit:main` |
| `skillclaw scrub` | `skillclaw_scrub.py` | `skillclaw.scrub:main` |
| `doctor` | (new) | core import smoke test; if `smoke.enabled`: require playwright; if `browser_use.enabled`: require `browser_use`; else warn only |

**Not in v1:** `generate-*`, `command-catalog`, `guidance-hint`, `budget-broker`, `reconcile`
(generators and bash-delegated tools stay as-is or gain subcommands later).

### Exit codes

Subcommands **preserve existing exit codes** where applicable. The router never
swallows `SystemExit` codes. (`cddl_loop.py` was retired; the shim exits 0 for
`--help`, 2 otherwise.)

---

## Bootstrap & deploy changes

### Replace `install_python_dependencies()`

Remove `pip install --user -r requirements.txt`. **Retire** `install_python_dependencies()`,
`install_smoke_deps()`, and `install_browser_use()` from `bootstrap/lib/install.sh` — smoke
and browser-use deps install only via `uv sync` groups. New `uv_sync_home_runtime()`:

1. Resolve `uv` to `$UV_BIN` (`command -v uv` or `"$HOME/.local/bin/uv"`).
2. Fail with actionable message if `$UV_BIN` missing.
3. Read **deployed** `$TARGET_DIR/config/services.yml` for `smoke.enabled` /
   `browser_use.enabled` to build group flags (same source of truth as `env-check`; CLI
   `--enable-smoke` / `--enable-browser-use` update `services.yml` before this runs).
   - `smoke.enabled: true` → `--group smoke`
   - `browser_use.enabled: true` → `--group smoke --group smoke-agent`
4. Run **one** `"$UV_BIN" sync --project "$TARGET_DIR" "${GROUP_FLAGS[@]}"`.
5. If smoke group installed: `"$TARGET_DIR/.venv/bin/playwright" install chromium`
   (replaces retired `install_smoke_deps()` browser step; idempotent).
6. Deploy a thin **`~/.local/bin/manifest` shell wrapper** (owned by `uv_sync_home_runtime`,
   not `deploy_configs` — needs `$UV_BIN` resolution):
   - resolves `uv` (`command -v uv` or `"$HOME/.local/bin/uv"`);
   - if missing: stderr `manifest: uv not found — re-run ./bootstrap.sh`; exit 1;
   - checks `~/.claude/.venv` exists (else stderr + exit 1);
   - `exec`s `"$HOME/.claude/.venv/bin/manifest" "$@"`.
7. Ensure `$HOME/.local/bin` on PATH (reuse existing profile logic).

`uv sync` is **idempotent** and safe on re-bootstrap.

### Deploy manifest

`deploy_configs` copies:

- `configs/claude/pyproject.toml` → `~/.claude/pyproject.toml` (project root, **not** under `scripts/`)
- `configs/claude/uv.lock` → `~/.claude/uv.lock`
- `configs/claude/scripts/` → `~/.claude/scripts/`
- `configs/claude/config/` → `~/.claude/config/` (includes `services.yml`)

**`bootstrap.sh` calls `uv_sync_home_runtime()` once** after deploy — not inside `deploy_configs`.

### Retire `requirements.txt`

Delete `configs/claude/scripts/requirements.txt` after migration (symlinked platform copies
follow). Document in bootstrap output: "Runtime deps: uv.lock @ ~/.claude".

---

## Deprecation shims (one release)

Each legacy `*.py` entry point becomes a **pure** Python shim (no in-process delegation):

1. Print **once per invocation** to stderr:
   `parallel_agent.py is deprecated; use: manifest parallel-agent`
2. **Fail closed** if `uv` (`shutil.which("uv")` or `~/.local/bin/uv`) or venv binary missing.
3. **Re-exec only** via `os.execv(os.path.expanduser("~/.claude/.venv/bin/manifest"),
   ["manifest", *subcommand.split(), *sys.argv[1:]])`. Never run logic under system `python3`.
4. **Preserve argv forwarding** byte-for-byte (skills embed exact flag sequences).

The `~/.local/bin/manifest` **shell wrapper** (not a `.py` shim) performs the same venv-exists
check before `exec`, so users get a friendly error even when `.venv` is absent.

`manifest_cli/__main__.py` supports `python -m manifest_cli` for debugging; production entry
is the console script inside the venv, reached via the wrapper.

**Shell wrappers** (`spec_review.sh`, `verification_gate.sh`, `skillclaw_promote.sh`,
`lifecycle.sh`) update to call `manifest …` directly in the **same release** (not via shims).
`deploy_reconcile.sh` is **not** a `manifest` subcommand in v1; it must use
`"$HOME/.claude/.venv/bin/python"` for **all** Python invocations (`reconcile_core.py` and
inline `-c` snippets) — no system `python3`.

**Release N+1:** remove shims; a missing shim is acceptable because docs/skills/hooks will
have migrated. Optional hard-fail stub: "removed; use manifest …".

---

## Error handling

| Condition | Behavior |
|-----------|----------|
| `~/.claude/.venv` missing | stderr: `manifest: home runtime not installed — re-run ./bootstrap.sh`; exit 1 |
| `uv` missing | stderr: `manifest: uv not found — re-run ./bootstrap.sh`; exit 1 |
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
- `manifest doctor` passes (imports core deps: `anthropic`, `yaml`, etc.)
- If `smoke.enabled` in `services.yml`: `doctor` requires playwright import
- If `browser_use.enabled`: `doctor` also requires `browser_use` import
- Otherwise missing optional deps are **warnings** only

Verdict: **BLOCKED** if any hard check fails (same severity as missing `~/.claude/skills`).

**Inline Python in `env-check`:** YAML/JSON validation snippets that today use system
`python3` must switch to `"$HOME/.claude/.venv/bin/python"` (or `manifest doctor`-grade
checks) so they do not depend on retired `pip install --user` packages.

---

## Testing

| Layer | What |
|-------|------|
| bats | `uv_sync_home_runtime` idempotency in SANDBOX with fake HOME |
| pytest | `manifest_cli` router: subcommand dispatch, argv passthrough, exit codes |
| pytest | shim prints deprecation, forwards to same exit code as canonical |
| CI | `uv lock --check` job: lockfile matches pyproject |
| pytest | `tests/python/test_requirements_drift.py`: `requirements-runtime.txt` + `requirements-smoke*.txt` pins match `uv.lock` groups |
| smoke-catalog | Update Lite-tier entry to invoke `manifest parallel-agent` (or `manifest smoke`) |

Repo CI **does not** switch to uv for pytest in v1; tests mock/stub `MANIFEST_HOME` and venv
paths where integration tests need them.

---

## Migration checklist (implementation)

1. Add `configs/claude/pyproject.toml` + generate `uv.lock`.
2. Move `skillclaw_*.py` implementations into `scripts/skillclaw/` package.
3. Add `manifest_cli` router + `manifest_cli/__main__.py` + `manifest doctor`.
4. Replace `install_python_dependencies`, `install_smoke_deps`, and `install_browser_use`
   with `uv_sync_home_runtime` (wrapper deploy owned here).
5. Extend `deploy_configs` to copy pyproject/lock/scripts; run `uv_sync_home_runtime` on bootstrap.
6. **Then** convert entry-point `.py` files to pure exec shims (venv + wrapper must exist).
7. Update shell wrappers (`spec_review.sh`, `verification_gate.sh`, `skillclaw_promote.sh`,
   `lifecycle.sh`) and `deploy_reconcile.sh` (venv python for **all** Python invocations);
   update high-traffic docs to `manifest …`.
8. Update `configs/claude/config/services.yml` smoke `command` to `manifest smoke` **and**
   the `write_services_config()` heredoc in `bootstrap/lib/config.sh` (prevents `--reconfigure`
   from reverting to `smoke_test.py`).
9. Extend `env-check` skill (venv python for inline checks + Home Python Runtime section).
10. Migrate `.skillshare/skills/` references from `parallel_agent.py` / `smoke_test.py` to
    `manifest parallel-agent` / `manifest smoke`.
11. Generate `tests/requirements-runtime.txt`; update CI test job to
    `pip install -r tests/requirements-ci.txt -r tests/requirements-runtime.txt`.
12. Remove `configs/claude/scripts/requirements.txt`; add `uv lock --check` + `uv build`
    CI steps and requirements drift test.
13. Replace retired installer calls in **both** `bootstrap.sh` paths (fresh + `--reconfigure`)
    with `uv_sync_home_runtime`.
14. Release N+1: delete shims.

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
| uv not installed on minimal hosts | **`ensure_uv()` unconditional** in bootstrap; fail-closed `env-check` |
| Slower first invoke | `uv sync` at bootstrap, not per invoke; venv bin is direct |
| Large lockfile churn | `uv lock --check` in CI; dependabot-style manual refresh |
| Click + asyncio (parallel-agent) | Router calls `asyncio.run(agents.cli.main())` once; `agents.cli` does not nest another loop |
| Python 3.14 / greenlet (smoke) | Keep existing playwright pin in smoke group |
