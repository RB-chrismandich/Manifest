import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

import manifest_cli.doctor as doctor_mod

WRAPPER_SRC = SCRIPTS / "manifest-cli.sh"


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


# --------------------------------------------------------------------------
# Dependency checks (explicit --services path: install integrity not audited)
# --------------------------------------------------------------------------


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
    _patch_imports(monkeypatch, failures={"yaml"})
    assert doctor_mod.run_doctor(services) == 1


def test_claude_enabled_requires_anthropic(tmp_path, monkeypatch):
    services = _write_services(
        tmp_path,
        """
        services:
          claude:
            enabled: true
        """,
    )
    _patch_imports(monkeypatch, failures={"anthropic"})
    assert doctor_mod.run_doctor(services) == 1


def test_every_core_module_is_checked(tmp_path, monkeypatch):
    """The yaml-only check was vacuous: doctor imported yaml at module scope, so a
    missing yaml crashed before the check ran. Each core module must be probed."""
    services = _write_services(tmp_path, "services: {}\n")
    for module in doctor_mod.CORE_MODULES:
        _patch_imports(monkeypatch, failures={module})
        assert doctor_mod.run_doctor(services) == 1, module


# --------------------------------------------------------------------------
# services.yml robustness — every one of these used to be a green run or a
# traceback
# --------------------------------------------------------------------------


def test_missing_services_file_fails(tmp_path, monkeypatch):
    _patch_imports(monkeypatch)
    rc = doctor_mod.run_doctor(tmp_path / "does-not-exist.yml")
    assert rc == 1


def test_malformed_services_file_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    services = tmp_path / "services.yml"
    services.write_text("services: {unclosed\n")
    _patch_imports(monkeypatch)
    assert doctor_mod.run_doctor(services) == 1
    assert "not valid YAML" in capsys.readouterr().err


def test_non_mapping_services_file_fails(tmp_path, monkeypatch, capsys):
    services = tmp_path / "services.yml"
    services.write_text("- one\n- two\n")
    _patch_imports(monkeypatch)
    assert doctor_mod.run_doctor(services) == 1
    assert "must contain a mapping" in capsys.readouterr().err


def test_empty_services_file_warns_but_passes(tmp_path, monkeypatch, capsys):
    services = tmp_path / "services.yml"
    services.write_text("")
    _patch_imports(monkeypatch)
    assert doctor_mod.run_doctor(services) == 0
    assert "is empty" in capsys.readouterr().err


def test_service_entry_of_wrong_shape_is_treated_as_disabled(tmp_path, monkeypatch):
    services = tmp_path / "services.yml"
    services.write_text("services:\n  smoke: true\n")
    _patch_imports(monkeypatch, failures={"playwright"})
    assert doctor_mod.run_doctor(services) == 0


def test_services_override_announces_that_integrity_is_unaudited(
    tmp_path, monkeypatch, capsys
):
    services = _write_services(tmp_path, "services: {}\n")
    _patch_imports(monkeypatch)
    doctor_mod.run_doctor(services)
    assert "install integrity not audited" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Install integrity — one deliberate breakage per test against a healthy tree
# --------------------------------------------------------------------------


@pytest.fixture
def healthy_root(tmp_path, monkeypatch):
    """A fully deployed runtime tree plus an installed, current wrapper."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MANIFEST_STATE_ROOT", str(home / ".manifest"))
    root = home / ".claude"
    (root / "config").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='manifest-runtime'\n")
    (root / "uv.lock").write_text("version = 1\n")
    _write_services(root / "config", "services: {}\n")
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python3").symlink_to(sys.executable)
    (venv_bin / "manifest").write_text("#!/bin/sh\nexit 0\n")
    (venv_bin / "manifest").chmod(0o755)
    (root / "scripts" / "manifest-cli.sh").write_text(WRAPPER_SRC.read_text())
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "manifest").write_text(WRAPPER_SRC.read_text())
    (bin_dir / "manifest").chmod(0o755)
    # Hermetic PATH: without this the developer's real ~/.local/bin/manifest
    # answers which("manifest") and the shadow/PATH findings become ambient.
    monkeypatch.setenv("PATH", str(bin_dir))
    (home / ".manifest").mkdir()
    (home / ".manifest" / "runtime.env").write_text(
        "clone_path=/repo\nhead_sha=abc1234\ndirty=false\n"
    )
    return root


def _report(root: Path, capsys) -> dict:
    rc = doctor_mod.run_doctor(root=root, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    payload["rc"] = rc
    return payload


def test_healthy_install_passes(healthy_root, monkeypatch, capsys):
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0, report["failures"]
    assert report["failures"] == []


def test_missing_runtime_root_fails(healthy_root, monkeypatch, capsys):
    _patch_imports(monkeypatch)
    report = _report(healthy_root.parent / "absent", capsys)
    assert report["rc"] == 1
    assert any("does not exist" in f for f in report["failures"])


@pytest.mark.parametrize("artifact", ["pyproject.toml", "uv.lock"])
def test_missing_deploy_artifact_fails(healthy_root, monkeypatch, capsys, artifact):
    (healthy_root / artifact).unlink()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any(artifact in f for f in report["failures"])


def test_missing_venv_fails(healthy_root, monkeypatch, capsys):
    for path in sorted(
        (healthy_root / ".venv").rglob("*"), key=lambda p: -len(p.parts)
    ):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    (healthy_root / ".venv").rmdir()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any("no venv at" in f for f in report["failures"])


def test_dead_venv_interpreter_fails(healthy_root, monkeypatch, capsys):
    (healthy_root / ".venv" / "bin" / "python3").unlink()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any("no interpreter" in f for f in report["failures"])


def test_missing_console_script_fails(healthy_root, monkeypatch, capsys):
    (healthy_root / ".venv" / "bin" / "manifest").unlink()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any("interrupted sync" in f for f in report["failures"])


def test_missing_wrapper_fails(healthy_root, monkeypatch, capsys):
    (Path.home() / ".local" / "bin" / "manifest").unlink()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any(".local/bin/manifest is missing" in f for f in report["failures"])


def test_non_executable_wrapper_fails(healthy_root, monkeypatch, capsys):
    (Path.home() / ".local" / "bin" / "manifest").chmod(0o644)
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 1
    assert any("not executable" in f for f in report["failures"])


def test_wrapper_drift_warns_without_failing(healthy_root, monkeypatch, capsys):
    (Path.home() / ".local" / "bin" / "manifest").write_text("#!/bin/sh\n# stale\n")
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any("differs from the deployed source" in w for w in report["warnings"])


def test_shadowed_wrapper_warns(healthy_root, monkeypatch, capsys):
    shadow_dir = Path.home() / "shadow"
    shadow_dir.mkdir()
    (shadow_dir / "manifest").write_text("#!/bin/sh\n")
    (shadow_dir / "manifest").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shadow_dir}:{Path.home() / '.local' / 'bin'}")
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any(str(shadow_dir / "manifest") in w for w in report["warnings"])


def test_wrapper_absent_from_path_warns_only(healthy_root, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(Path.home() / "empty"))
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any("not on PATH" in w for w in report["warnings"])


def test_missing_uv_warns_only(healthy_root, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(Path.home() / "empty"))
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any("uv not found" in w for w in report["warnings"])


def test_dirty_deploy_warns(healthy_root, monkeypatch, capsys):
    (Path.home() / ".manifest" / "runtime.env").write_text(
        "clone_path=/repo\ndirty=true\n"
    )
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any("dirty clone" in w for w in report["warnings"])


def test_unstamped_install_warns(healthy_root, monkeypatch, capsys):
    (Path.home() / ".manifest" / "runtime.env").unlink()
    _patch_imports(monkeypatch)
    report = _report(healthy_root, capsys)
    assert report["rc"] == 0
    assert any("no deploy stamp" in w for w in report["warnings"])
