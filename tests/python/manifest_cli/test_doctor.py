import sys
from pathlib import Path
from textwrap import dedent

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

import manifest_cli.doctor as doctor_mod


def _write_services(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "services.yml"
    path.write_text(dedent(body).lstrip())
    return path


def _patch_imports(monkeypatch, *, failures: set[str] | None = None):
    failures = failures or set()

    def fake_try_import(module: str) -> str | None:
        if module in failures:
            return "not installed"
        return None

    monkeypatch.setattr(doctor_mod, "_try_import", fake_try_import)


def test_core_imports_pass(tmp_path, monkeypatch):
    services = _write_services(
        tmp_path,
        """
        services:
          smoke:
            enabled: false
          browser_use:
            enabled: false
        """,
    )
    _patch_imports(monkeypatch)
    assert doctor_mod.run_doctor(services) == 0


def test_smoke_enabled_requires_playwright(tmp_path, monkeypatch):
    services = _write_services(
        tmp_path,
        """
        services:
          smoke:
            enabled: true
        """,
    )
    _patch_imports(monkeypatch, failures={"playwright"})
    assert doctor_mod.run_doctor(services) == 1


def test_browser_use_enabled_requires_browser_use(tmp_path, monkeypatch):
    services = _write_services(
        tmp_path,
        """
        services:
          browser_use:
            enabled: true
        """,
    )
    _patch_imports(monkeypatch, failures={"browser_use"})
    assert doctor_mod.run_doctor(services) == 1


def test_optional_deps_not_required_when_disabled(tmp_path, monkeypatch):
    services = _write_services(
        tmp_path,
        """
        services:
          smoke:
            enabled: false
          browser_use:
            enabled: false
        """,
    )
    _patch_imports(monkeypatch, failures={"playwright", "browser_use"})
    assert doctor_mod.run_doctor(services) == 0


def test_core_import_failure(tmp_path, monkeypatch):
    services = _write_services(tmp_path, "services: {}\n")
    _patch_imports(monkeypatch, failures={"anthropic"})
    assert doctor_mod.run_doctor(services) == 1
