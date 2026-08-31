# manifest uv CLI Implementation Plan

**Status: COMPLETED — shipped; audited by evidence 2026-07-29 (11/11 tasks verified).**

> **Do not execute this plan.** It is kept as the implementation record. The step
> checkboxes below still read `- [ ]` because the original execution never ticked them —
> that staleness is the artifact's, not the feature's. A `/spec-audit-tasks` pass on
> 2026-07-29 verified all 11 tasks against the tree instead (files present, tests green,
> no stubs) and found two real gaps, both since closed:
>
> | Task | Gap found | Closed by |
> |------|-----------|-----------|
> | Task 7 | `deploy_reconcile.sh:91` fell back to system `python3`, contradicting the spec's "no fail-open to system `python3`" | Spec amended with a scoped, **enforced** exception (design doc, Revision 2026-07-29): the fallback is necessary (reconcile runs at `bootstrap.sh:293`, before the venv exists at `:297`) and safe (`reconcile_core.py` is stdlib-only), pinned by `test_reconcile_core_has_no_hard_third_party_imports` |
> | Task 9 | 6 skill sites still routed through the deprecated `parallel_agent.py` shim — they would have broken at "Release N+1: delete shims" | Repointed to `manifest parallel-agent` (`issue-triage`, `issue-prioritize`: 3 command sites + 3 dispatch-guidance mentions) |
>
> Step-level boxes were deliberately **not** bulk-ticked: several are process steps
> ("Run tests — expect FAIL") whose occurrence cannot be verified after the fact, and
> ticking them would assert knowledge nobody has. Per-task verdicts above are
> evidence-backed; the boxes are not.
>
> Still open by design: design-checklist item 14, "Release N+1: delete shims".

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a uv-managed home runtime at `~/.claude/.venv` with a unified `manifest` CLI, replacing `pip install --user` and eliminating missing-package / host-Python-pollution / pin-drift failures for deployed Python tools.

**Architecture:** Add `configs/claude/pyproject.toml` + committed `uv.lock`; bootstrap runs `uv_sync_home_runtime()` (reads `services.yml` groups, `uv sync`, optional `playwright install chromium`, deploys `~/.local/bin/manifest` shell wrapper). New `manifest_cli` Click router delegates to existing packages (`agents`, `smoke_orchestrator`, `cddl`, `skillclaw`). Legacy `*.py` entry points become exec-only shims for one release.

**Tech Stack:** uv, Hatchling, Click, Bash (`set -euo pipefail`), BATS, pytest.

**Spec:** `docs/superpowers/specs/2026-07-13-manifest-uv-cli-design.md`

**Working directory:** repo root. Paths below are repo-relative unless noted.

## Global Constraints

- Home runtime project root: `configs/claude/` → deployed `~/.claude/` (`pyproject.toml` and `uv.lock` at **root**, not under `scripts/`).
- **No fail-open to system `python3`** for home-runtime tools; shims use `os.execv` to venv `manifest` only.
- `check_uv()` runs **unconditionally** in bootstrap (existing `bootstrap/lib/install.sh` helper).
- Retire `install_python_dependencies()`, `install_smoke_deps()`, `install_browser_use()`; smoke browser via `"$TARGET_DIR/.venv/bin/playwright" install chromium` when smoke group installed.
- `browser_use.enabled: true` → `uv sync --group smoke --group smoke-agent` (both groups).
- `pyyaml` is a **core** dependency (not smoke-only).
- `~/.local/bin/manifest` is a **shell wrapper**, not a symlink into `.venv`. ~~(checks uv + venv)~~
  **Superseded 2026-07-29:** the wrapper checks only what `exec` needs (runtime root → venv →
  entry point → `+x` → shebang target) and **never** checks uv. Measured: `check_uv()` installs
  uv outside a minimal PATH, so the uv check turned every launchd/cron/hook caller into a hard
  failure against a healthy runtime. uv is reported by `manifest doctor` as a warning. See the
  design doc's "Revision 2026-07-29 — the wrapper no longer gates on `uv`".
- Repo CI stays on `pip` for pytest; additive CI steps only (`uv lock --check`, `uv build`, drift test).
- Preserve existing exit codes (especially `cddl` 0/2/3/4/5/6/7).

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `configs/claude/pyproject.toml` | Create | Runtime deps, groups, hatch wheel mapping, `[project.scripts]` |
| `configs/claude/uv.lock` | Create | Pinned resolution (committed) |
| `configs/claude/scripts/manifest_cli/__init__.py` | Create | Click router `main()` |
| `configs/claude/scripts/manifest_cli/__main__.py` | Create | `python -m manifest_cli` entry |
| `configs/claude/scripts/manifest_cli/doctor.py` | Create | Import checks keyed off `services.yml` |
| `configs/claude/scripts/manifest-cli.sh` | Create | Source for `~/.local/bin/manifest` wrapper |
| `configs/claude/scripts/skillclaw/` | Create | Package moved from top-level `skillclaw_*.py` |
| `configs/claude/scripts/skillclaw_*.py` | Modify | Pure exec shims (Task 8) |
| `configs/claude/scripts/parallel_agent.py` | Modify | Pure exec shim |
| `configs/claude/scripts/smoke_test.py` | Modify | Pure exec shim |
| `configs/claude/scripts/cddl_loop.py` | Modify | Pure exec shim |
| `bootstrap/lib/install.sh` | Modify | Add `uv_sync_home_runtime()`, remove retired installers |
| `bootstrap/lib/deploy.sh` | Modify | Copy pyproject/lock; call `deploy_manifest_wrapper` hook |
| `bootstrap.sh` | Modify | `check_uv` unconditional; replace installer calls |
| `bootstrap/lib/config.sh` | Modify | `write_services_config()` smoke command → `manifest smoke` |
| `configs/claude/config/services.yml` | Modify | `smoke.command: manifest smoke` |
| `configs/claude/scripts/spec_review.sh` | Modify | `manifest parallel-agent` default |
| `configs/claude/scripts/verification_gate.sh` | Modify | `manifest parallel-agent` in review seam |
| `configs/claude/scripts/lifecycle.sh` | Modify | `manifest smoke` default |
| `configs/claude/scripts/deploy_reconcile.sh` | Modify | Venv python for all Python |
| `configs/claude/scripts/skillclaw_promote.sh` | Modify | `manifest skillclaw …` where applicable |
| `.retired skill supply/skills/**/SKILL.md` | Modify | `manifest parallel-agent` / `manifest smoke` |
| `configs/claude/CLAUDE.md` | Modify | Document `manifest` CLI |
| `configs/cursor/rules/orchestration.mdc` | Regenerate | Via `generate_cursor_rules.sh` after skill edits |
| `.retired skill supply/skills/env-check/SKILL.md` | Modify | Home Python Runtime + venv python snippets |
| `tests/bats/uv_sync_home_runtime.bats` | Create | SANDBOX bootstrap seam tests |
| `tests/bats/manifest_wrapper.bats` | Create | Wrapper fail-closed tests |
| `tests/python/manifest_cli/test_router.py` | Create | Subcommand dispatch |
| `tests/python/manifest_cli/test_doctor.py` | Create | Conditional smoke checks |
| `tests/python/manifest_cli/test_shims.py` | Create | Deprecation + execv seam |
| `tests/python/test_requirements_drift.py` | Create | CI pin parity |
| `tests/requirements-runtime.txt` | Create | Core runtime pins for CI |
| `.github/workflows/ci.yml` | Modify | `uv lock --check`, `uv build`, runtime reqs |
| `configs/claude/scripts/requirements.txt` | Delete | Replaced by pyproject |

---

### Task 1: Runtime `pyproject.toml` + `uv.lock`

**Files:**
- Create: `configs/claude/pyproject.toml`
- Create: `configs/claude/uv.lock` (generated)
- Delete later: `configs/claude/scripts/requirements.txt` (Task 12)

**Interfaces:**
- Produces: installable project `manifest-runtime` with console script `manifest = "manifest_cli:main"`

- [ ] **Step 1: Create `configs/claude/pyproject.toml`**

```toml
[project]
name = "manifest-runtime"
version = "0.0.0"
description = "Manifest home-deployed Python runtime"
requires-python = ">=3.11"
dependencies = [
  "anthropic>=0.40.0",
  "google-genai>=1.0.0; python_version >= '3.9'",
  "google-generativeai>=0.8.0",
  "google-auth>=2.0.0",
  "aiohttp>=3.9.0",
  "asyncio-throttle>=1.0.0",
  "pyyaml>=6.0.1",
  "jsonschema>=4.23.0",
  "rich>=13.0.0",
  "click>=8.1.0",
  "psutil>=5.9.0",
]

[project.scripts]
manifest = "manifest_cli:main"

[dependency-groups]
smoke = ["playwright==1.60.0"]
smoke-agent = ["browser-use>=0.13.0"]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
  "scripts/agents",
  "scripts/smoke_orchestrator",
  "scripts/cddl",
  "scripts/skillclaw",
  "scripts/manifest_cli",
]

[tool.hatch.build.targets.wheel.sources]
"scripts/agents" = "agents"
"scripts/smoke_orchestrator" = "smoke_orchestrator"
"scripts/cddl" = "cddl"
"scripts/skillclaw" = "skillclaw"
"scripts/manifest_cli" = "manifest_cli"
```

- [ ] **Step 2: Add stub `manifest_cli` package so lock resolves**

Create minimal files (filled in Task 3):

`configs/claude/scripts/manifest_cli/__init__.py`:

```python
def main() -> None:
    raise SystemExit("manifest_cli not yet implemented")
```

`configs/claude/scripts/manifest_cli/__main__.py`:

```python
from manifest_cli import main

main()
```

Create empty `configs/claude/scripts/skillclaw/__init__.py` (implementations in Task 2).

- [ ] **Step 3: Generate lockfile**

```bash
cd configs/claude && uv lock
```

Expected: `configs/claude/uv.lock` created with no errors.

- [ ] **Step 4: Verify build**

```bash
uv build --project configs/claude
```

Expected: wheel builds; `manifest` entry point present.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/pyproject.toml configs/claude/uv.lock \
  configs/claude/scripts/manifest_cli configs/claude/scripts/skillclaw/__init__.py
git commit -m "feat(runtime): add configs/claude pyproject and uv.lock"
```

---

### Task 2: Move skillclaw implementations into package

**Files:**
- Create: `configs/claude/scripts/skillclaw/ingest.py` (from `skillclaw_ingest.py`)
- Create: `configs/claude/scripts/skillclaw/evolve.py`, `promote.py`, `audit.py`, `scrub.py`
- Modify: `configs/claude/scripts/skillclaw_promote.sh` imports (if any direct paths)
- Test: `tests/python/test_skillclaw_*.py` (update imports if needed)

**Interfaces:**
- Produces: `skillclaw.ingest.main(argv)`, `skillclaw.evolve.main(argv)`, etc. (same signatures as today)

- [ ] **Step 1: Move modules**

For each file, move body from `configs/claude/scripts/skillclaw_<name>.py` into
`configs/claude/scripts/skillclaw/<name>.py`. Keep `main(argv)` signatures unchanged.
Add re-export in `skillclaw/__init__.py` only if tests import package-level symbols.

- [ ] **Step 2: Run existing skillclaw tests**

```bash
python3 -m pytest tests/python/test_skillclaw_ingest.py tests/python/test_skillclaw_evolve.py \
  tests/python/test_skillclaw_promote.py tests/python/test_skillclaw_audit.py \
  tests/python/test_skillclaw_scrub.py -q
```

Expected: PASS (fix import paths in tests if they referenced old module names).

- [ ] **Step 3: Commit**

```bash
git add configs/claude/scripts/skillclaw/ tests/python/test_skillclaw_*.py
git commit -m "refactor(skillclaw): move implementations into skillclaw package"
```

---

### Task 3: `manifest_cli` Click router + `doctor`

**Files:**
- Modify: `configs/claude/scripts/manifest_cli/__init__.py`
- Create: `configs/claude/scripts/manifest_cli/doctor.py`
- Test: `tests/python/manifest_cli/test_router.py`, `tests/python/manifest_cli/test_doctor.py`

**Interfaces:**
- Produces: `manifest_cli.main()` — Click group; subcommands delegate to existing `main()` fns
- Produces: `manifest_cli.doctor.run(services_yml: Path) -> int`

- [ ] **Step 1: Write failing router tests**

`tests/python/manifest_cli/test_router.py`:

```python
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

from click.testing import CliRunner
from manifest_cli import cli


def test_help_lists_parallel_agent():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "parallel-agent" in result.output


def test_cddl_delegates_argv(monkeypatch):
    captured = {}

    def fake_main(argv=None):
        captured["argv"] = list(argv or [])
        return 0

    monkeypatch.setattr("cddl.cli.main", fake_main)
    result = CliRunner().invoke(cli, ["cddl", "status"])
    assert result.exit_code == 0
    assert captured["argv"] == ["status"]
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
python3 -m pytest tests/python/manifest_cli/test_router.py -v
```

- [ ] **Step 3: Implement router**

`configs/claude/scripts/manifest_cli/__init__.py`:

```python
import asyncio
import sys
from pathlib import Path

import click

from manifest_cli.doctor import run_doctor


@click.group()
def cli() -> None:
    """Manifest home-runtime CLI."""


@cli.command("parallel-agent", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def parallel_agent(args: tuple[str, ...]) -> None:
    from agents.cli import main as agents_main

    sys.argv = ["manifest parallel-agent", *args]
    raise SystemExit(asyncio.run(agents_main()))


@cli.command("smoke", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def smoke(args: tuple[str, ...]) -> None:
    from smoke_orchestrator.cli import main as smoke_main

    sys.argv = ["manifest smoke", *args]
    raise SystemExit(smoke_main())


@cli.command("cddl", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def cddl(args: tuple[str, ...]) -> None:
    from cddl.cli import main as cddl_main

    raise SystemExit(cddl_main(list(args)))


@cli.group()
def skillclaw() -> None:
    """SkillClaw tools."""


def _skillclaw_cmd(module: str, args: tuple[str, ...]) -> None:
    import importlib

    mod = importlib.import_module(f"skillclaw.{module}")
    raise SystemExit(mod.main(list(args)))


@skillclaw.command("ingest", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_ingest(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("ingest", args)


@skillclaw.command("evolve", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_evolve(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("evolve", args)


@skillclaw.command("promote", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_promote(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("promote", args)


@skillclaw.command("audit", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_audit(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("audit", args)


@skillclaw.command("scrub", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_scrub(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("scrub", args)


@cli.command("doctor")
@click.option(
    "--services",
    type=click.Path(path_type=Path),
    default=Path.home() / ".claude/config/services.yml",
)
def doctor(services: Path) -> None:
    raise SystemExit(run_doctor(services))


def main() -> None:
    cli(prog_name="manifest")


if __name__ == "__main__":
    main()
```

`configs/claude/scripts/manifest_cli/doctor.py` — import `anthropic`, `yaml`; if
`services.yml` has `smoke.enabled: true` require `playwright`; if `browser_use.enabled`
require `browser_use`; return 0/1.

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest tests/python/manifest_cli/ -v
```

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/manifest_cli tests/python/manifest_cli
git commit -m "feat(manifest): add Click router and doctor subcommand"
```

---

### Task 4: `uv_sync_home_runtime()` + `manifest-cli.sh` wrapper

**Files:**
- Modify: `bootstrap/lib/install.sh`
- Create: `configs/claude/scripts/manifest-cli.sh`
- Test: `tests/bats/uv_sync_home_runtime.bats`, `tests/bats/manifest_wrapper.bats`

**Interfaces:**
- Produces: `uv_sync_home_runtime()` — idempotent; uses `$TARGET_DIR`, `$UV_BIN`
- Produces: deployed `~/.local/bin/manifest` from `manifest-cli.sh`

- [ ] **Step 1: Write failing bats for wrapper**

`tests/bats/manifest_wrapper.bats` — fake HOME without `.venv`, run wrapper, expect
stderr contains `home runtime not installed` and exit 1.

- [ ] **Step 2: Create `configs/claude/scripts/manifest-cli.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

err() { printf 'manifest: %s\n' "$*" >&2; }

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV_BIN="${HOME}/.local/bin/uv"
else
  err "uv not found — re-run ./bootstrap.sh"
  exit 1
fi

VENV_MANIFEST="${HOME}/.claude/.venv/bin/manifest"
if [[ ! -x "$VENV_MANIFEST" ]]; then
  err "home runtime not installed — re-run ./bootstrap.sh"
  exit 1
fi

exec "$VENV_MANIFEST" "$@"
```

- [ ] **Step 3: Add `uv_sync_home_runtime()` to `bootstrap/lib/install.sh`**

```bash
uv_sync_home_runtime() {
    local target_dir="${TARGET_DIR:-$HOME/.claude}"
    local uv_bin=""
    if command_exists uv; then
        uv_bin="$(command -v uv)"
    elif [[ -x "$HOME/.local/bin/uv" ]]; then
        uv_bin="$HOME/.local/bin/uv"
    else
        print_warning "uv not found — skipping home runtime sync"
        return 0
    fi

    local -a group_flags=()
    local services_yml="$target_dir/config/services.yml"
    if [[ -f "$services_yml" ]]; then
        if python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('1' if d.get('services',{}).get('smoke',{}).get('enabled') else '0')" "$services_yml" | grep -q 1; then
            group_flags+=(--group smoke)
        fi
        if python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); print('1' if d.get('services',{}).get('browser_use',{}).get('enabled') else '0')" "$services_yml" | grep -q 1; then
            group_flags+=(--group smoke --group smoke-agent)
        fi
    fi

    print_step "Syncing home Python runtime (uv)..."
    if ! "$uv_bin" sync --project "$target_dir" "${group_flags[@]}"; then
        print_warning "uv sync failed — parallel agent may be unavailable"
        return 0
    fi

    if [[ " ${group_flags[*]} " == *" smoke "* ]]; then
        "$target_dir/.venv/bin/playwright" install chromium || print_warning "playwright install chromium failed"
    fi

    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/configs/claude/scripts/manifest-cli.sh" "$HOME/.local/bin/manifest"
    chmod +x "$HOME/.local/bin/manifest"
    print_success "Home runtime synced; manifest CLI at ~/.local/bin/manifest"
}
```

Add `deploy_manifest_wrapper` call at end (wrapper copy is inside `uv_sync_home_runtime`).

- [ ] **Step 4: Write `tests/bats/uv_sync_home_runtime.bats`** with SANDBOX HOME + mock `uv`.

- [ ] **Step 5: Run bats**

```bash
bats tests/bats/manifest_wrapper.bats tests/bats/uv_sync_home_runtime.bats
```

- [ ] **Step 6: Commit**

```bash
git add bootstrap/lib/install.sh configs/claude/scripts/manifest-cli.sh tests/bats/
git commit -m "feat(bootstrap): add uv_sync_home_runtime and manifest shell wrapper"
```

---

### Task 5: Wire bootstrap + deploy

**Files:**
- Modify: `bootstrap.sh` (both install paths ~lines 171–173 and 282–284)
- Modify: `bootstrap/lib/deploy.sh` — ensure pyproject/lock copied (rsync from `configs/claude/`)

**Interfaces:**
- Consumes: `uv_sync_home_runtime()` from Task 4
- Produces: bootstrap calls `check_uv` unconditionally before deploy

- [ ] **Step 1: Replace installer trio in `bootstrap.sh`**

Replace:

```bash
install_python_dependencies
install_browser_use
install_smoke_deps
```

With:

```bash
uv_sync_home_runtime
```

In **both** fresh-install and `--reconfigure` paths.

- [ ] **Step 2: Ensure `check_uv` runs unconditionally**

Verify `bootstrap.sh` invokes `check_uv` before deploy (not gated on `--enable-graphify`).

- [ ] **Step 3: Copy pyproject + lock in deploy**

In `deploy_configs`, after rsync of claude tree, ensure:

```bash
cp "$SCRIPT_DIR/configs/claude/pyproject.toml" "$TARGET_DIR/pyproject.toml"
cp "$SCRIPT_DIR/configs/claude/uv.lock" "$TARGET_DIR/uv.lock"
```

(Idempotent with rsync if already included — verify paths land at `$TARGET_DIR/` root.)

- [ ] **Step 4: Manual smoke test (developer machine)**

```bash
./bootstrap.sh --skip-auth --force
manifest --help
manifest doctor
```

- [ ] **Step 5: Commit**

```bash
git add bootstrap.sh bootstrap/lib/deploy.sh
git commit -m "feat(bootstrap): wire uv_sync_home_runtime; deploy pyproject at home root"
```

---

### Task 6: Deprecation shims for legacy `.py` entry points

**Files:**
- Modify: `parallel_agent.py`, `smoke_test.py`, `cddl_loop.py`, `skillclaw_*.py`
- Test: `tests/python/manifest_cli/test_shims.py`

**Interfaces:**
- Consumes: `~/.claude/.venv/bin/manifest` (must exist — Task 5 complete)

- [ ] **Step 1: Shared shim helper**

Create `configs/claude/scripts/_manifest_shim.py`:

```python
import os
import shutil
import sys
import warnings


def exec_manifest(subcommand: str, legacy_name: str) -> None:
    warnings.warn(
        f"{legacy_name} is deprecated; use: manifest {subcommand}",
        DeprecationWarning,
        stacklevel=2,
    )
    if not shutil.which("uv") and not os.path.isfile(
        os.path.expanduser("~/.local/bin/uv")
    ):
        print(
            "parallel_agent.py: uv not found — re-run ./bootstrap.sh", file=sys.stderr
        )
        raise SystemExit(1)
    manifest_bin = os.path.expanduser("~/.claude/.venv/bin/manifest")
    if not os.path.isfile(manifest_bin):
        print(
            f"{legacy_name}: home runtime not installed — re-run ./bootstrap.sh",
            file=sys.stderr,
        )
        raise SystemExit(1)
    os.execv(manifest_bin, ["manifest", *subcommand.split(), *sys.argv[1:]])
```

- [ ] **Step 2: Replace each entry point**

Example `parallel_agent.py`:

```python
#!/usr/bin/env python3
from _manifest_shim import exec_manifest

if __name__ == "__main__":
    exec_manifest("parallel-agent", "parallel_agent.py")
```

Apply analogous subcommands for `smoke`, `cddl`, `skillclaw ingest`, etc.

- [ ] **Step 3: Test shims with mocked execv**

- [ ] **Step 4: Commit**

```bash
git add configs/claude/scripts/_manifest_shim.py configs/claude/scripts/*.py tests/python/manifest_cli/test_shims.py
git commit -m "feat(manifest): add deprecation shims for legacy python entry points"
```

---

### Task 7: Update shell wrappers to `manifest` / venv python

**Files:**
- Modify: `spec_review.sh`, `verification_gate.sh`, `lifecycle.sh`, `skillclaw_promote.sh`, `deploy_reconcile.sh`

- [ ] **Step 1: `spec_review.sh`**

Change default:

```bash
SPEC_REVIEW_PANEL_CMD="${SPEC_REVIEW_PANEL_CMD:-manifest parallel-agent}"
```

(Or keep path to script but invoke `manifest parallel-agent` when file is `parallel_agent.py`.)

- [ ] **Step 2: `verification_gate.sh`**

Default review seam:

```bash
cmd_str="${VERIFICATION_GATE_REVIEW_CMD:-manifest parallel-agent --json --validate --timeout 600 --review}"
```

- [ ] **Step 3: `lifecycle.sh`**

```bash
SMOKE_CMD="${LIFECYCLE_SMOKE_CMD:-manifest smoke}"
```

- [ ] **Step 4: `deploy_reconcile.sh`**

At top after `SCRIPT_DIR`:

```bash
VENV_PY="${MANIFEST_VENV_PY:-${HOME}/.claude/.venv/bin/python}"
```

Replace every `python3` invocation with `"$VENV_PY"`.

- [ ] **Step 5: Run targeted bats/shellcheck**

```bash
shellcheck -S warning configs/claude/scripts/spec_review.sh configs/claude/scripts/verification_gate.sh \
  configs/claude/scripts/lifecycle.sh configs/claude/scripts/deploy_reconcile.sh
```

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/*.sh
git commit -m "refactor(scripts): call manifest CLI and venv python from shell wrappers"
```

---

### Task 8: `services.yml` + bootstrap template

**Files:**
- Modify: `configs/claude/config/services.yml`
- Modify: `bootstrap/lib/config.sh` (`write_services_config` heredoc)

- [ ] **Step 1: Update committed `services.yml`**

```yaml
  smoke:
    enabled: false
    command: manifest smoke
```

- [ ] **Step 2: Update `write_services_config()` heredoc** — same `command: manifest smoke`.

- [ ] **Step 3: Commit**

```bash
git add configs/claude/config/services.yml bootstrap/lib/config.sh
git commit -m "chore(services): point smoke service at manifest smoke command"
```

---

### Task 9: Skills, orchestration docs, env-check

**Files:**
- Modify: `.retired skill supply/skills/**/SKILL.md` (parallel_agent / smoke_test references)
- Modify: `.retired skill supply/skills/env-check/SKILL.md`
- Modify: `configs/claude/CLAUDE.md`, `AGENTS.md` orchestration sections
- Run: `configs/claude/scripts/generate_cursor_rules.sh`

- [ ] **Step 1: Bulk replace in skills**

```bash
# Review then apply — prefer manifest subcommands:
# ~/.claude/scripts/parallel_agent.py → manifest parallel-agent
# ~/.claude/scripts/smoke_test.py → manifest smoke
# configs/claude/scripts/smoke_test.py → manifest smoke (repo-relative examples)
```

Use `rg -l 'parallel_agent\.py|smoke_test\.py' .retired skill supply/skills` and update each SKILL.

- [ ] **Step 2: env-check skill**

Add **Home Python Runtime** section: `uv`, `~/.claude/.venv`, `manifest`, `manifest doctor`.
Change inline `python3 -c` YAML checks to `"$HOME/.claude/.venv/bin/python"`.

- [ ] **Step 3: Regenerate cursor rules**

```bash
configs/claude/scripts/generate_cursor_rules.sh
```

- [ ] **Step 4: Commit**

```bash
git add .retired skill supply/skills configs/claude/CLAUDE.md AGENTS.md configs/cursor/rules
git commit -m "docs(skills): migrate to manifest CLI; extend env-check runtime checks"
```

---

### Task 10: CI — runtime requirements, drift test, uv gates

**Files:**
- Create: `tests/requirements-runtime.txt`
- Create: `tests/python/test_requirements_drift.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Export `tests/requirements-runtime.txt`**

Mirror core deps from `configs/claude/pyproject.toml` with exact pins from `uv.lock`.
Header comment: `# sync-with: configs/claude/uv.lock`

- [ ] **Step 2: Drift test**

```python
# tests/python/test_requirements_drift.py — parse requirements-runtime.txt and
# smoke*.txt; assert package names exist in uv.lock dependency groups.
```

- [ ] **Step 3: CI workflow**

In test job:

```yaml
- run: pip install -r tests/requirements-ci.txt -r tests/requirements-runtime.txt
```

In lint job (additive):

```yaml
- run: pip install uv && uv lock --check --project configs/claude
- run: uv build --project configs/claude
```

- [ ] **Step 4: Run locally**

```bash
python3 -m pytest tests/python/test_requirements_drift.py -v
uv lock --check --project configs/claude
```

- [ ] **Step 5: Commit**

```bash
git add tests/requirements-runtime.txt tests/python/test_requirements_drift.py .github/workflows/ci.yml
git commit -m "ci: add uv lock/build gates and runtime requirements drift test"
```

---

### Task 11: Remove retired `requirements.txt` + installer dead code

**Files:**
- Delete: `configs/claude/scripts/requirements.txt`
- Modify: `bootstrap/lib/install.sh` — remove `install_python_dependencies`, `install_smoke_deps`, `install_browser_use` bodies

- [ ] **Step 1: Delete requirements.txt**

- [ ] **Step 2: Remove dead functions** (grep repo for callers — should be none after Task 5)

- [ ] **Step 3: Full verification**

```bash
bats tests/bats/
python3 -m pytest tests/python/ -q
shellcheck -S warning bootstrap.sh bootstrap/lib/*.sh configs/claude/scripts/*.sh
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(runtime): remove pip --user requirements and retired installers"
```

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| uv.lock at `configs/claude/` | Task 1 |
| skillclaw package before shims | Task 2 |
| manifest CLI subcommands | Task 3 |
| uv_sync + playwright chromium | Task 4 |
| bootstrap wiring | Task 5 |
| exec-only shims | Task 6 |
| shell wrappers + reconcile venv python | Task 7 |
| services.yml + config.sh template | Task 8 |
| skills + env-check | Task 9 |
| CI coexistence + drift | Task 10 |
| retire requirements.txt | Task 11 |
| Error handling: optional group not installed → `smoke deps not installed — re-run ./bootstrap.sh --enable-smoke`; exit 1 | **Was missing from this table** — no task implemented it, so the shipped router raised a bare `ModuleNotFoundError` traceback for a full release. Added 2026-07-29: `manifest_cli.guarded_imports` (per-group toggle hints + incomplete-runtime message), covered by `tests/python/manifest_cli/test_router.py` |
| Error handling: `~/.claude/.venv` / `uv` missing, exit codes | Task 4 (wrapper) + Task 6 (shims); contract revised 2026-07-29 — see the design doc's error-handling table |
| Release N+1 shim removal | **Future** — not in this plan |

No TBD placeholders. Task order respects “venv before shims”.

**Coverage lesson (2026-07-29 audit).** This table was the only spec↔task mapping, and one
Error-handling row of the design never appeared in it — so nothing flagged that the friendly
"optional group not installed" message was never built. A design row that reaches no task is
invisible to every later audit that trusts this table. When amending the design's error-handling
table, add the row here in the same change.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-13-manifest-uv-cli.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — execute tasks in this session with executing-plans checkpoints

Which approach?
