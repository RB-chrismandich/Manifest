"""Linux-native behavioral tests for cgroup-v2 delegate containment."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from _delegate_harness import _run
from _delegate_inproc import delegate

containment = delegate.containment


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux containment venue"
)
@pytest.mark.native
def test_linux_ci_requires_writable_cgroup_venue():
    if not os.environ.get("CI"):
        pytest.skip("local Linux lacks the delegated CI venue")
    available, reason = containment.probe()
    assert available, reason


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_reap_kills_double_setsid_descendant(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    path, state, _reason = containment.create(str(job_dir))
    assert state == containment.STATE_CONTAINED
    script = "import os,sys,time; os.setsid();\nif os.fork()==0:\n os.setsid(); print(os.getpid(),flush=True); time.sleep(300)"
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        text=True,
        preexec_fn=lambda: containment.join(path),
    )
    child = int(proc.stdout.readline().strip())
    proc.wait(timeout=30)
    assert containment.reap(str(job_dir)) is True
    for _ in range(100):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("cgroup reap did not kill double-setsid descendant")
    assert containment.cleanup(str(job_dir)) is True


def _wait_for_path(path, description):
    deadline = time.time() + 10
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    pytest.fail(f"{description} was not created")


def _assert_dead(pid, description):
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"{description} remained alive")


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_timeout_reaps_double_setsid_descendant_through_worker(tmp_path, env_factory):
    pidfile = tmp_path / "timeout.pid"
    env = env_factory(control={"detached_holder_secs": 300, "sleep": 300})
    env["MANIFEST_CGROUP_ROOT"] = containment.cgroup_root()
    env["STUB_DETACHED_PIDFILE"] = str(pidfile)
    env["STUB_DETACHED_CLOSE_STREAMS"] = "1"
    config_path = Path(env["MANIFEST_CONFIG_DIR"]) / "delegation.json"
    config_path.write_text(
        '{"default_backend":"stub","backends":{"stub":{"budget_seconds":1}}}'
    )

    result = _run(env, "task", "--json", "timeout")

    assert result.returncode == 1, result.stderr
    _wait_for_path(pidfile, "double-setsid descendant pidfile")
    pid = int(pidfile.read_text())
    _assert_dead(pid, "timeout descendant")
    record_path = next(Path(env["MANIFEST_DELEGATIONS_DIR"]).rglob("record.json"))
    job_dir = record_path.parent
    assert not (job_dir / containment.CGROUP_DIR_FILENAME).exists()


@pytest.mark.native
@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and containment.probe()[0]),
    reason="requires delegated cgroup v2",
)
def test_cancel_reaps_double_setsid_descendant_through_cmd_cancel(
    tmp_path, env_factory
):
    pidfile = tmp_path / "cancel.pid"
    env = env_factory(control={"detached_holder_secs": 300, "sleep": 300})
    env["MANIFEST_CGROUP_ROOT"] = containment.cgroup_root()
    env["STUB_DETACHED_PIDFILE"] = str(pidfile)
    env["STUB_DETACHED_CLOSE_STREAMS"] = "1"
    launched = _run(env, "task", "--background", "--json", "cancel")
    assert launched.returncode == 0, launched.stderr
    record_path = next(Path(env["MANIFEST_DELEGATIONS_DIR"]).rglob("record.json"))
    _wait_for_path(pidfile, "double-setsid descendant pidfile")
    job_dir = record_path.parent
    marker = job_dir / containment.CGROUP_DIR_FILENAME
    _wait_for_path(marker, "containment marker")

    cancelled = _run(env, "cancel", job_dir.name, "--json")

    assert cancelled.returncode == 0, cancelled.stderr
    _assert_dead(int(pidfile.read_text()), "cancelled descendant")
    deadline = time.time() + 5
    while marker.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert not marker.exists()
