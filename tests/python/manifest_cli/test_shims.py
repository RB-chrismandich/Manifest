import runpy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

import _manifest_shim


MANIFEST_HOME = "~/.claude/.venv/bin/manifest"
LOCAL_UV = "~/.local/bin/uv"


def _patch_runtime(monkeypatch, tmp_path, *, uv: bool = True, manifest: bool = True):
    if uv:
        monkeypatch.setattr(_manifest_shim.shutil, "which", lambda cmd: "/usr/bin/uv" if cmd == "uv" else None)
    else:
        monkeypatch.setattr(_manifest_shim.shutil, "which", lambda cmd: None)

    manifest_bin = tmp_path / "manifest"
    if manifest:
        manifest_bin.write_text("#!/bin/sh\n")

    def expanduser(path: str) -> str:
        if path == MANIFEST_HOME:
            return str(manifest_bin)
        if path == LOCAL_UV:
            return str(tmp_path / "uv")
        return path

    def isfile(path: str) -> bool:
        if path == str(manifest_bin):
            return manifest
        if path == str(tmp_path / "uv"):
            return uv and not _manifest_shim.shutil.which("uv")
        return False

    monkeypatch.setattr(_manifest_shim.os.path, "expanduser", expanduser)
    monkeypatch.setattr(_manifest_shim.os.path, "isfile", isfile)
    return manifest_bin


def test_exec_manifest_warns_and_execs(monkeypatch, tmp_path):
    manifest_bin = _patch_runtime(monkeypatch, tmp_path)
    captured = {}

    def fake_execv(bin_path, args):
        captured["bin"] = bin_path
        captured["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(_manifest_shim.os, "execv", fake_execv)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["parallel_agent.py", "--json", "prompt"])

    with pytest.warns(DeprecationWarning, match=r"parallel_agent\.py is deprecated; use: manifest parallel-agent"):
        with pytest.raises(SystemExit) as exc:
            _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert exc.value.code == 0
    assert captured["bin"] == str(manifest_bin)
    assert captured["args"] == ["manifest", "parallel-agent", "--json", "prompt"]


def test_exec_manifest_splits_multiword_subcommand(monkeypatch, tmp_path):
    _patch_runtime(monkeypatch, tmp_path)
    captured = {}

    def fake_execv(_bin, args):
        captured["args"] = args
        raise SystemExit(0)

    monkeypatch.setattr(_manifest_shim.os, "execv", fake_execv)
    monkeypatch.setattr(_manifest_shim.sys, "argv", ["skillclaw_ingest.py", "in", "out"])

    with pytest.warns(DeprecationWarning):
        with pytest.raises(SystemExit):
            _manifest_shim.exec_manifest("skillclaw ingest", "skillclaw_ingest.py")

    assert captured["args"] == ["manifest", "skillclaw", "ingest", "in", "out"]


def test_exec_manifest_exits_when_uv_missing(monkeypatch, tmp_path, capsys):
    _patch_runtime(monkeypatch, tmp_path, uv=False, manifest=True)

    with pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("parallel-agent", "parallel_agent.py")

    assert exc.value.code == 1
    assert "uv not found" in capsys.readouterr().err


def test_exec_manifest_exits_when_manifest_missing(monkeypatch, tmp_path, capsys):
    _patch_runtime(monkeypatch, tmp_path, uv=True, manifest=False)

    with pytest.raises(SystemExit) as exc:
        _manifest_shim.exec_manifest("smoke", "smoke_test.py")

    assert exc.value.code == 1
    assert "home runtime not installed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("script", "subcommand", "legacy"),
    [
        ("parallel_agent.py", "parallel-agent", "parallel_agent.py"),
        ("smoke_test.py", "smoke", "smoke_test.py"),
        ("cddl_loop.py", "cddl", "cddl_loop.py"),
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
