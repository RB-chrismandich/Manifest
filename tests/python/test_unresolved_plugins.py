"""T4.5 (spec 674) — naming installed plugins whose cache directory is gone.

The helper shipped with no tests at all. The distinction that matters is between
its three exit states: 0 means "checked, here is the answer" (possibly empty), 3
means "cannot tell". Collapsing those two is how a corrupt plugins state after a
restore reads as a clean one.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs/claude/scripts/unresolved_plugins.py"
)
_spec = importlib.util.spec_from_file_location("unresolved_plugins", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _state(tmp_path, plugins) -> str:
    f = tmp_path / "installed_plugins.json"
    f.write_text(json.dumps({"version": 1, "plugins": plugins}))
    return str(f)


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_a_missing_install_path_is_named(tmp_path):
    path = _state(tmp_path, {"a@m": [{"installPath": str(tmp_path / "gone")}]})
    assert mod.unresolved(path) == ["a@m"]


def test_a_present_install_path_is_not_named(tmp_path):
    live = tmp_path / "here"
    live.mkdir()
    path = _state(tmp_path, {"a@m": [{"installPath": str(live)}]})
    assert mod.unresolved(path) == []


def test_an_empty_plugins_map_is_clean(tmp_path):
    assert mod.unresolved(_state(tmp_path, {})) == []


def test_malformed_json_raises_unreadable_rather_than_returning_clean(tmp_path):
    f = tmp_path / "installed_plugins.json"
    f.write_text("{not json")
    with pytest.raises(mod.Unreadable):
        mod.unresolved(str(f))


def test_absent_file_raises_unreadable(tmp_path):
    with pytest.raises(mod.Unreadable):
        mod.unresolved(str(tmp_path / "absent.json"))


def test_exit_3_means_cannot_tell(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    result = _run(str(f))
    assert result.returncode == 3
    assert "cannot read state" in result.stderr
    assert result.stdout == ""


def test_exit_0_with_empty_output_means_checked_and_clean(tmp_path):
    result = _run(_state(tmp_path, {}))
    assert result.returncode == 0
    assert result.stdout == ""


def test_help_exits_zero_without_running(tmp_path):
    # `--help` used to be passed straight through as a filename: it printed
    # nothing and exited 0, so the tool silently ran instead of describing
    # itself, and the help-coverage gate could not see the difference.
    result = _run("--help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_no_argument_is_a_usage_error_not_a_silent_success():
    result = _run()
    assert result.returncode == 2
    assert "Usage:" in result.stderr
