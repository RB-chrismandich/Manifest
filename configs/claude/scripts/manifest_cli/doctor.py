"""manifest doctor — home-runtime dependency and install-integrity checks.

Two classes of finding, deliberately separated:

* **failures** (exit 1) — environment-independent breakage: a missing deploy
  artifact, an unimportable module, an unreadable services.yml. env-check maps
  these to BLOCKED.
* **warnings** (exit 0) — true observations that depend on the calling context or
  on user intent: `manifest` absent from *this* process's PATH, a shadowing
  binary, wrapper drift, uv missing. Reported, never silently dropped.

A skipped check is never reported as a pass: when `--services` points somewhere
other than the deployed tree, the install audit is announced as not run.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from pathlib import Path

from manifest_cli.runtime import (
    deployed_wrapper_source,
    install_stamp,
    runtime_root,
    uv_path,
    venv_dir,
    version_line,
    wrapper_path,
)

# Cheap core imports that a partially-applied `uv sync` leaves behind. Heavier
# SDKs (google-genai) are deliberately excluded: they cost seconds to import and
# their absence surfaces through the same guarded_imports path at call time.
CORE_MODULES = ("yaml", "click", "aiohttp", "rich")

OPTIONAL_SERVICE_DEPS = (
    ("claude", "anthropic", "uv sync --group claude"),
    ("smoke", "playwright", "./bootstrap.sh --enable-smoke"),
    ("browser_use", "browser_use", "./bootstrap.sh --enable-browser-use"),
)


class Report:
    """Accumulates findings so every check runs before anything is printed."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _try_import(module: str) -> str | None:
    try:
        importlib.import_module(module)
        return None
    except ImportError as exc:
        return str(exc)


def _service_enabled(data: dict, name: str) -> bool:
    services = data.get("services")
    if not isinstance(services, dict):
        return False
    svc = services.get(name)
    if not isinstance(svc, dict):
        return False
    return bool(svc.get("enabled", False))


def _load_services(path: Path, report: Report) -> dict:
    """Read services.yml, reporting every way it can be unusable.

    A missing file used to read as "every optional service disabled", which turned
    a half-deleted runtime tree into a green doctor run.
    """
    err = _try_import("yaml")
    if err:
        report.fail(f"cannot read {path}: PyYAML is missing from the runtime ({err})")
        return {}
    import yaml

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        report.fail(
            f"services.yml is missing at {path} — the deploy is incomplete; "
            f"re-run ./bootstrap.sh"
        )
        return {}
    except OSError as exc:
        report.fail(f"cannot read {path}: {exc}")
        return {}

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        report.fail(f"{path} is not valid YAML: {first_line}")
        return {}

    if data is None:
        report.warn(f"{path} is empty — treating all optional services as disabled")
        return {}
    if not isinstance(data, dict):
        report.fail(
            f"{path} must contain a mapping, found {type(data).__name__}; "
            f"re-run ./bootstrap.sh --reconfigure"
        )
        return {}
    if "services" not in data:
        report.warn(f"{path} has no 'services' key — treating all as disabled")
    return data


def _check_core_imports(report: Report) -> None:
    for module in CORE_MODULES:
        err = _try_import(module)
        if err:
            report.fail(
                f"core dependency '{module}' is missing from the runtime venv "
                f"({err}); re-run ./bootstrap.sh"
            )


def _check_optional_deps(data: dict, report: Report) -> None:
    for service, module, remedy in OPTIONAL_SERVICE_DEPS:
        if not _service_enabled(data, service):
            continue
        err = _try_import(module)
        if err:
            report.fail(
                f"{service}.enabled requires '{module}' ({remedy}): {err}",
            )


def _check_layout(root: Path, report: Report) -> None:
    if not root.is_dir():
        report.fail(f"runtime root {root} does not exist; re-run ./bootstrap.sh")
        return

    for artifact in ("pyproject.toml", "uv.lock"):
        if not (root / artifact).is_file():
            report.fail(
                f"{root / artifact} is missing — the deploy is incomplete, so "
                f"`uv sync` cannot converge the venv; re-run ./bootstrap.sh"
            )

    venv = venv_dir(root)
    if not venv.is_dir():
        report.fail(f"no venv at {venv}; re-run ./bootstrap.sh")
        return

    interpreters = [venv / "bin" / name for name in ("python3", "python")]
    if not any(path.is_file() for path in interpreters):
        report.fail(
            f"the venv at {venv} has no interpreter (Python was upgraded away, or "
            f"the tree was copied from another home); re-run ./bootstrap.sh"
        )
    if not (venv / "bin" / "manifest").is_file():
        report.fail(
            f"{venv / 'bin' / 'manifest'} is missing (interrupted sync); "
            f"re-run ./bootstrap.sh"
        )
    # Running outside the deployed venv means these findings describe some other
    # environment — say so rather than let the report read as authoritative.
    if Path(sys.prefix).resolve() != venv.resolve():
        report.warn(
            f"doctor is running from {sys.prefix}, not the deployed venv "
            f"({venv}) — dependency results describe that environment"
        )


def _check_wrapper(root: Path, report: Report) -> None:
    wrapper = wrapper_path()
    if not wrapper.is_file():
        report.fail(
            f"{wrapper} is missing — every documented `manifest …` call site "
            f"resolves through it; re-run ./bootstrap.sh"
        )
    else:
        if not os.access(wrapper, os.X_OK):
            report.fail(f"{wrapper} is not executable; re-run ./bootstrap.sh")
        source = deployed_wrapper_source(root)
        if source.is_file():
            try:
                drifted = source.read_bytes() != wrapper.read_bytes()
            except OSError as exc:
                report.warn(f"could not compare {wrapper} with {source}: {exc}")
            else:
                if drifted:
                    report.warn(
                        f"{wrapper} differs from the deployed source ({source}) — "
                        f"re-run ./bootstrap.sh to refresh it"
                    )

    resolved = shutil.which("manifest")
    if resolved is None:
        report.warn(
            "`manifest` is not on PATH in this process — add "
            f"{wrapper.parent} to PATH (login shells get it from your profile)"
        )
    elif Path(resolved).resolve() != wrapper.resolve():
        report.warn(f"PATH resolves `manifest` to {resolved}, shadowing {wrapper}")


def _check_tooling(root: Path, report: Report) -> None:
    if uv_path() is None:
        report.warn(
            "uv not found — the installed runtime still runs, but re-syncing or "
            "re-running ./bootstrap.sh needs it"
        )
    stamp = install_stamp(root)
    if not stamp:
        report.warn(
            "no deploy stamp — this runtime's provenance is unknown "
            "(re-run ./bootstrap.sh to record it)"
        )
    elif stamp.get("dirty") == "true":
        report.warn(
            f"deployed from a dirty clone ({stamp.get('clone_path', 'unknown')}) — "
            "the runtime may not match any commit"
        )


def run_doctor(
    services_yml: Path | None = None,
    *,
    root: Path | None = None,
    as_json: bool = False,
) -> int:
    """Run dependency checks, plus install integrity when a real tree is in scope.

    The install audit runs when doctor resolves the runtime tree itself (the CLI
    path) or when a caller names a root explicitly (tests, fixtures). An explicit
    ``--services`` pointing elsewhere disables it — and says so.
    """
    inspect_install = root is not None or services_yml is None
    root = root or runtime_root()
    if services_yml is None:
        services_yml = root / "config" / "services.yml"

    report = Report()
    _check_core_imports(report)
    data = _load_services(Path(services_yml), report)
    _check_optional_deps(data, report)
    if inspect_install:
        _check_layout(root, report)
        _check_wrapper(root, report)
        _check_tooling(root, report)
    else:
        report.note(
            f"install integrity not audited — --services points at {services_yml}, "
            f"outside the deployed tree"
        )

    ok = not report.failures
    if as_json:
        json.dump(
            {
                "ok": ok,
                "version": version_line(),
                "root": str(root),
                "services": str(services_yml),
                "failures": report.failures,
                "warnings": report.warnings,
                "notes": report.notes,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0 if ok else 1

    for msg in report.notes:
        print(f"manifest doctor: note: {msg}", file=sys.stderr)
    for msg in report.warnings:
        print(f"manifest doctor: warning: {msg}", file=sys.stderr)
    for msg in report.failures:
        print(f"manifest doctor: {msg}", file=sys.stderr)
    if ok:
        print(f"manifest doctor: ok — {version_line()}")
    return 0 if ok else 1


run = run_doctor
