import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

from click.testing import CliRunner
from manifest_cli import cli, guarded_imports


def test_help_lists_parallel_agent():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "parallel-agent" in result.output


def test_help_does_not_list_retired_cddl():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "cddl" not in result.output


def test_version_reports_runtime_facts():
    """`manifest --version` used to exit 2 on an unknown option, leaving callers
    with no way to assert which runtime is installed."""
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "manifest-runtime" in result.output
    assert "python" in result.output
    assert "root" in result.output


def test_version_lookup_is_lazy(monkeypatch):
    """click.version_option evaluates its version at import time, which charged
    every invocation ~13ms of importlib.metadata lookup for an unused string."""
    import importlib.metadata as md

    calls: list[str] = []
    real = md.version
    monkeypatch.setattr(md, "version", lambda name: (calls.append(name), real(name))[1])

    CliRunner().invoke(cli, ["--help"])
    assert calls == []
    CliRunner().invoke(cli, ["--version"])
    assert calls == ["manifest-runtime"]


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("playwright", "--enable-smoke"),
        ("playwright._impl", "--enable-smoke"),
        ("browser_use", "--enable-browser-use"),
        ("anthropic", "--enable-claude"),
    ],
)
def test_missing_optional_group_names_its_toggle(module, expected, capsys):
    with pytest.raises(SystemExit) as exc, guarded_imports():
        raise ModuleNotFoundError(f"No module named '{module}'", name=module)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert expected in err
    assert "Traceback" not in err


def test_missing_core_module_reports_an_incomplete_runtime(capsys):
    with pytest.raises(SystemExit) as exc, guarded_imports():
        raise ModuleNotFoundError("No module named 'aiohttp'", name="aiohttp")
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "home runtime is incomplete" in err
    assert "aiohttp" in err


def test_guard_does_not_swallow_subcommand_exit_codes():
    with pytest.raises(SystemExit) as exc, guarded_imports():
        raise SystemExit(3)
    assert exc.value.code == 3


def test_guard_does_not_swallow_real_errors():
    with pytest.raises(ValueError), guarded_imports():
        raise ValueError("a genuine bug")


def test_subcommand_missing_dependency_exits_one(monkeypatch):
    """End-to-end through the router: an unimportable group is one line, not a
    traceback the caller has to read."""

    def boom(_name):
        raise ModuleNotFoundError("No module named 'playwright'", name="playwright")

    monkeypatch.setattr(importlib, "import_module", boom)
    result = CliRunner().invoke(cli, ["skillclaw", "ingest", "src"])
    assert result.exit_code == 1
    assert "--enable-smoke" in result.output


def test_doctor_json_output_is_machine_readable(tmp_path):
    services = tmp_path / "services.yml"
    services.write_text("services: {}\n")
    result = CliRunner().invoke(cli, ["doctor", "--services", str(services), "--json"])
    assert result.exit_code == 0
    assert '"ok": true' in result.output
