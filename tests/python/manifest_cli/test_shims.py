import os
import runpy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

import _manifest_shim


def _make_runtime(
    tmp_path: Path, monkeypatch, *, installed: bool = True, executable: bool = True
) -> Path:
    """Build a real runtime tree and point the shim at it via MANIFEST_HOME.

    Patching os.path internals would have the shim agree with the test about a
    filesystem neither of them touched; a real tree is what the shim actually
    stats in production.
    """
    root = tmp_path / "claude"
    monkeypatch.setenv("MANIFEST_HOME", str(root))
    monkeypatch.setenv("MANIFEST_STATE_ROOT", str(tmp_path / "state"))
    manifest_bin = root / ".venv" / "bin" / "manifest"
    if installed:
        manifest_bin.parent.mkdir(parents=True)
        manifest_bin.write_text("#!/bin/sh\nexit 0\n")
        manifest_bin.chmod(0o755 if executable else 0o644)
    else:
        root.mkdir(parents=True)
    return manifest_bin


def test_exec_manifest_warns_and_execs(monkeypatch, tmp_path):
    manifest_bin = _make_runtime(tmp_path, monkeypatch)
    captured = {}

    def fake_execv(bin_path, args):
        captured["bin"] = bin_path
        captured["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(_manifest_shim.os, "execv", fake_execv)
    monkeypatch.setattr(
        _manifest_shim.sys, "argv", ["parallel_agent.py", "--json", "prompt"]
    )

    with (
        pytest.warns(
            DeprecationWarning,
            match=r"parallel_agent\.py is deprecated; use: manifest parallel-agent",
        ),
        pytest.raises(SystemExit) as exc,
    ):
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert exc.value.code == 0
    assert captured["bin"] == str(manifest_bin)
    assert captured["args"] == ["manifest", "parallel-agent", "--json", "prompt"]


def test_exec_manifest_splits_multiword_subcommand(monkeypatch, tmp_path):
    _make_runtime(tmp_path, monkeypatch)
    captured = {}

    def fake_execv(_bin, args):
        captured["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(_manifest_shim.os, "execv", fake_execv)
    monkeypatch.setattr(
        _manifest_shim.sys, "argv", ["skillclaw_ingest.py", "in", "out"]
    )

    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit):
        _manifest_shim.exec_manifest("skillclaw ingest", "skillclaw_ingest.py")

    assert captured["args"] == ["manifest", "skillclaw", "ingest", "in", "out"]


def test_runs_when_uv_is_absent(monkeypatch, tmp_path):
    """uv installs the runtime; it is never needed to execute an installed one."""
    _make_runtime(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["parallel_agent.py"])
    execed = {}

    def fake_execv(bin_path, _args):
        execed["bin"] = bin_path
        raise SystemExit(0)

    monkeypatch.setattr(_manifest_shim.os, "execv", fake_execv)
    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")
    assert exc.value.code == 0
    assert execed["bin"].endswith("/.venv/bin/manifest")


def test_exec_manifest_exits_when_manifest_missing(monkeypatch, tmp_path, capsys):
    _make_runtime(tmp_path, monkeypatch, installed=False)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["smoke_test.py"])

    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("smoke", "smoke_test.py")

    assert exc.value.code == 1
    assert "home runtime not installed" in capsys.readouterr().err


def test_exec_manifest_reports_lost_executable_bit(monkeypatch, tmp_path, capsys):
    _make_runtime(tmp_path, monkeypatch, executable=False)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["smoke_test.py"])

    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("smoke", "smoke_test.py")

    assert exc.value.code == 1
    assert "not executable" in capsys.readouterr().err


def test_execv_failure_is_reported_not_raised(monkeypatch, tmp_path, capsys):
    """A runtime that exists but cannot exec (dead interpreter, wrong arch)."""
    _make_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["parallel_agent.py"])

    def boom(_bin, _args):
        raise OSError(8, "Exec format error")

    monkeypatch.setattr(_manifest_shim.os, "execv", boom)
    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "could not start the home runtime" in err
    assert "Exec format error" in err


def test_error_names_the_deploying_clone(monkeypatch, tmp_path, capsys):
    _make_runtime(tmp_path, monkeypatch, installed=False)
    clone = tmp_path / "Manifest"
    clone.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (state / "runtime.env").write_text(f"clone_path={clone}\n")
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["parallel_agent.py"])

    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit):
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert f"re-run {clone / 'bootstrap.sh'}" in capsys.readouterr().err


def test_help_path_survives_a_missing_runtime(monkeypatch, tmp_path, capsys):
    """cli-help-before-dependency-checks: --help must work in a clean env."""
    _make_runtime(tmp_path, monkeypatch, installed=False)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["parallel_agent.py", "--help"])

    with pytest.warns(DeprecationWarning), pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert exc.value.code == 0
    assert "deprecated shim" in capsys.readouterr().out


def test_runtime_root_defaults_to_claude_home(monkeypatch):
    monkeypatch.delenv("MANIFEST_HOME", raising=False)
    assert _manifest_shim._runtime_root() == os.path.expanduser("~/.claude")


@pytest.mark.parametrize(
    ("script", "subcommand", "legacy"),
    [
        ("parallel_agent.py", "parallel-agent", "parallel_agent.py"),
        ("smoke_test.py", "smoke", "smoke_test.py"),
        ("skillclaw_ingest.py", "skillclaw ingest", "skillclaw_ingest.py"),
        ("skillclaw_evolve.py", "skillclaw evolve", "skillclaw_evolve.py"),
        ("skillclaw_promote.py", "skillclaw promote", "skillclaw_promote.py"),
        ("skillclaw_audit.py", "skillclaw audit", "skillclaw_audit.py"),
        ("skillclaw_scrub.py", "skillclaw scrub", "skillclaw_scrub.py"),
    ],
)
def test_legacy_entry_points_delegate(script, subcommand, legacy, monkeypatch):
    calls = []
    monkeypatch.setattr(
        _manifest_shim,
        "exec_manifest",
        lambda cmd, name: calls.append((cmd, name)),
    )
    runpy.run_path(str(SCRIPTS / script), run_name="__main__")
    assert calls == [(subcommand, legacy)]


def test_cddl_loop_retired():
    sys.argv = ["cddl_loop.py", "start", "specs/001-fx"]
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPTS / "cddl_loop.py"), run_name="__main__")
    assert exc.value.code == 2


def test_cddl_loop_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        sys.argv = ["cddl_loop.py", "--help"]
        runpy.run_path(str(SCRIPTS / "cddl_loop.py"), run_name="__main__")
    assert exc.value.code == 0
