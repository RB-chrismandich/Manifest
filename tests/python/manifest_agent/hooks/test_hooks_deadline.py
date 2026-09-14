"""The adapter's deadline is `checks.process.run_argv`'s real process-group
kill — the exact function `hooks/runner.py::run_manifest_check` calls, not a
reimplementation. This proves that mechanism kills a grandchild that
outlives its own parent, using real subprocesses (no mocking of `os.killpg`,
`subprocess`, or time)."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import signal
import sys
import time

from .conftest import write_custom_check_project


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno != errno.ESRCH
    return True


def test_deadline_kills_a_grandchild_that_outlives_its_parent(tmp_path):
    from manifest_agent.checks.process import run_argv

    grandchild_marker = tmp_path / "grandchild-ran"
    pid_file = tmp_path / "pids.json"
    script = tmp_path / "spawn_and_block.py"
    script.write_text(
        "import json, os, subprocess, sys, time\n"
        "grandchild = subprocess.Popen([sys.executable, '-c',\n"
        "    'import pathlib,time; time.sleep(6); "
        'pathlib.Path(%r).write_text("done")\' % sys.argv[1]])\n'
        "with open(sys.argv[2], 'w') as fh:\n"
        "    json.dump({'self': os.getpid(), 'grandchild': grandchild.pid}, fh)\n"
        "time.sleep(20)\n",
        encoding="utf-8",
    )

    start = time.monotonic()
    # subprocess-env: exempt -- synthetic tmp_path script, no
    # manifest_agent/tools import.
    result = run_argv(
        (sys.executable, str(script), str(grandchild_marker), str(pid_file)),
        cwd=tmp_path,
        env={"PATH": os.defpath},
        timeout_seconds=1.5,
    )
    elapsed = time.monotonic() - start

    assert result.timed_out is True
    assert elapsed < 6, (
        "run_argv must return at its deadline, not wait for the grandchild"
    )

    import json

    for _ in range(50):
        if pid_file.exists():
            break
        time.sleep(0.05)
    pids = json.loads(pid_file.read_text(encoding="utf-8"))

    # Give the killed grandchild the time it would have needed to finish its
    # sleep-then-write if it had survived; the marker must never appear.
    time.sleep(6)
    assert not grandchild_marker.exists(), "grandchild survived the deadline kill"
    assert not _pid_exists(pids["self"])
    assert not _pid_exists(pids["grandchild"])


def test_adapter_deadline_kills_the_check_body_process_group(
    hook_harness, tmp_path
) -> None:
    marker = tmp_path / "escaped-check-body"
    started = tmp_path / "check-body-started"
    grandchild = (
        "import pathlib,time; time.sleep(3); "
        f"pathlib.Path({str(marker)!r}).write_text('escaped')"
    )
    body = tmp_path / "slow_check.py"
    body.write_text(
        "import subprocess, sys, time\n"
        f"open({str(started)!r}, 'w').write('started')\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    config = hook_harness.root / "config/deadline-project-checks.json"
    write_custom_check_project(config, body)
    payload = {
        "session_id": "deadline",
        "cwd": str(hook_harness.root),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "a.txt"},
    }

    start = time.monotonic()
    result = hook_harness.invoke(
        "claude-code",
        "PostToolUse",
        payload,
        MANIFEST_HOOK_PROJECT_CONFIG=str(config),
        MANIFEST_HOOK_TIMEOUT_SECONDS="1.5",
    )

    assert time.monotonic() - start < 3
    response = json.loads(result.stdout)
    assert response["decision"] == "block"
    assert started.exists(), "deadline expired before the check body started"
    time.sleep(3)
    assert not marker.exists(), "check body escaped the adapter deadline"


def test_check_launch_error_becomes_blocked_result(tmp_path) -> None:
    from manifest_agent.checks.models import Candidate, CheckSpec
    from manifest_agent.checks.runner import execute_check

    check = CheckSpec(
        id="check.missing",
        group="shared",
        category="test",
        argv=("manifest-definitely-missing",),
        cwd=".",
        inputs=("a.txt",),
        dependencies=(),
        timeout_seconds=1,
        selection="always",
        tool="missing",
        version="1",
    )
    candidate = Candidate(tmp_path, "digest", "head", "tree")

    result = execute_check(check, candidate, {"PATH": os.defpath}, {})

    assert result.status == "BLOCKED"
    assert result.returncode is None
    assert result.diagnostics


def test_timeout_drain_is_bounded_when_a_detached_descendant_holds_pipes(
    tmp_path,
) -> None:
    from manifest_agent.checks.process import run_argv

    pid_file = tmp_path / "detached.pid"
    child_code = (
        "import os,time;"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()));"
        "time.sleep(10)"
    )
    script = tmp_path / "detach.py"
    script.write_text(
        "import subprocess,sys,time\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}], start_new_session=True)\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )

    start = time.monotonic()
    result = run_argv(
        (sys.executable, str(script)),
        tmp_path,
        {"PATH": os.defpath},
        0.2,
    )
    elapsed = time.monotonic() - start

    try:
        assert result.timed_out is True
        assert elapsed < 1.5
        assert result.error and "detached descendants" in result.error
    finally:
        if pid_file.exists():
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
