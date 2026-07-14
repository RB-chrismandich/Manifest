"""manifest doctor — home-runtime dependency checks."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml


def _service_enabled(data: dict, name: str) -> bool:
    services = data.get("services", {})
    svc = services.get(name, {})
    return bool(svc.get("enabled", False))


def _try_import(module: str) -> str | None:
    try:
        importlib.import_module(module)
        return None
    except ImportError as exc:
        return str(exc)


def run_doctor(services_yml: Path) -> int:
    """Run import smoke tests; optional groups keyed off services.yml."""
    failures: list[str] = []

    for module in ("anthropic", "yaml"):
        err = _try_import(module)
        if err:
            failures.append(f"missing core dependency {module}: {err}")

    if services_yml.is_file():
        data = yaml.safe_load(services_yml.read_text()) or {}
    else:
        data = {}

    if _service_enabled(data, "smoke"):
        err = _try_import("playwright")
        if err:
            failures.append(f"smoke.enabled requires playwright: {err}")

    if _service_enabled(data, "browser_use"):
        err = _try_import("browser_use")
        if err:
            failures.append(f"browser_use.enabled requires browser_use: {err}")

    for msg in failures:
        print(f"manifest doctor: {msg}", file=sys.stderr)

    return 1 if failures else 0


run = run_doctor
