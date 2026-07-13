"""US1 — verification-before-critique gate (T016, FR-009; research D8)."""

import json
import shlex
from unittest.mock import MagicMock

import pytest
from cddl.verify import detect_cmds, run_verification


def test_detect_bats(tmp_path):
    (tmp_path / "tests" / "bats").mkdir(parents=True)
    assert "bats tests/bats/" in detect_cmds(tmp_path)


def test_detect_pytest_via_tests_python(tmp_path):
    (tmp_path / "tests" / "python").mkdir(parents=True)
    assert "pytest" in detect_cmds(tmp_path)


def test_detect_pytest_via_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    assert "pytest" in detect_cmds(tmp_path)


def test_detect_npm_only_with_test_script(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
    assert "npm test -s" in detect_cmds(tmp_path)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
    assert "npm test -s" not in detect_cmds(tmp_path)


def test_detect_make_only_with_test_target(tmp_path):
    (tmp_path / "Makefile").write_text("test:\n\techo ok\n")
    assert "make test" in detect_cmds(tmp_path)
    (tmp_path / "Makefile").write_text("build:\n\techo ok\n")
    assert "make test" not in detect_cmds(tmp_path)


def test_multiple_detections_in_sequence(tmp_path):
    (tmp_path / "tests" / "bats").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    cmds = detect_cmds(tmp_path)
    assert cmds.index("bats tests/bats/") < cmds.index("pytest")


def test_no_gates_disclosed_skip(tmp_path):
    log = tmp_path / "verify.log"
    result = run_verification(tmp_path, None, log)
    assert result.ran is False
    assert result.passed is True
    assert result.cmds == []
    assert "no verification gates" in log.read_text().lower()


def test_verify_cmd_override_passes(tmp_path):
    log = tmp_path / "verify.log"
    result = run_verification(tmp_path, "echo gate-ok", log)
    assert result.ran and result.passed
    assert result.cmds == ["echo gate-ok"]
    assert "gate-ok" in log.read_text()


def test_verify_cmd_override_fails(tmp_path):
    log = tmp_path / "verify.log"
    result = run_verification(tmp_path, "false", log)
    assert result.ran and not result.passed
    assert "[exit 1]" in log.read_text()


def test_verify_cmd_shell_metacharacters_are_literal(tmp_path):
    log = tmp_path / "verify.log"
    result = run_verification(tmp_path, "echo boom && exit 3", log)
    assert result.ran and result.passed
    assert "boom && exit 3" in log.read_text()


def test_sequence_stops_at_first_failure(tmp_path):
    # auto-detected gates run in sequence; a failure short-circuits
    (tmp_path / "tests" / "bats").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("")
    log = tmp_path / "verify.log"
    result = run_verification(
        tmp_path, None, log, command_runner=lambda cmd: (1, f"ran {cmd}\n")
    )
    assert result.ran and not result.passed
    assert result.cmds == ["bats tests/bats/"]  # pytest never ran


def test_command_runs_in_repo_cwd(tmp_path):
    log = tmp_path / "verify.log"
    run_verification(tmp_path, "pwd", log)
    assert str(tmp_path.resolve()) in log.read_text()


@pytest.mark.parametrize(
    "cmd",
    [
        "bats tests/bats/",
        "pytest",
        "npm test -s",
        "make test",
    ],
)
def test_default_runner_splits_auto_detected_cmds(cmd, tmp_path, monkeypatch):
    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": argv, "shell": kwargs.get("shell")})
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = f"ran {' '.join(argv)}\n"
        proc.stderr = ""
        return proc

    monkeypatch.setattr("cddl.verify.subprocess.run", fake_run)
    log = tmp_path / "verify.log"
    result = run_verification(tmp_path, cmd, log)
    assert result.ran and result.passed
    assert len(calls) == 1
    assert calls[0]["shell"] is False
    assert calls[0]["argv"] == shlex.split(cmd)
    assert f"ran {cmd}" in log.read_text()
