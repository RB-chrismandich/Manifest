"""Isolation tests for the weekly health_report.py collector."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    HealthyReportRunner,
    collect_report,
    healthy_harness_record,
    isolated_env,
    load_runtime_module,
    workspace_bundle,
    write_report_fixture,
)


@pytest.fixture
def report_bundle() -> Path:
    """The manifest-workspace plugin directory that ships health_report.py."""
    return workspace_bundle()


def _report_script(bundle: Path) -> Path:
    return bundle / "skills/env-check/scripts/health_report.py"


def _collect_report_fixture(tmp_path: Path, bundle: Path):
    module = load_runtime_module(
        _report_script(bundle), f"health_report_{tmp_path.name}"
    )
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    env, runtime_root, receipt = write_report_fixture(tmp_path, now)
    report = collect_report(module, env, runtime_root, now, HealthyReportRunner(module))
    return module, report, env, runtime_root, receipt, now


def test_weekly_health_report_accepts_only_complete_fresh_evidence_and_retains_twelve(
    report_bundle: Path, tmp_path: Path
) -> None:
    """A fully healthy fixture reports ok everywhere and rotates weekly files."""
    module, report, env, _runtime_root, _receipt, _now = _collect_report_fixture(
        tmp_path, report_bundle
    )

    assert report["schema_version"] == 1
    assert report["status"] == "ok"
    assert report["findings"] == []
    assert report["receipt"]["status"] == "ok"
    assert report["harnesses"]["claude"]["status"] == "ok"
    assert report["harnesses"]["omp"]["status"] == "ok"
    assert report["mcp"]["claude"]["status"] == "ok"
    assert report["hooks"]["status"] == "ok"
    assert report["pins"]["status"] == "ok"

    out_dir = Path(env["XDG_STATE_HOME"]) / "manifest/reports"
    out_dir.mkdir(parents=True)
    for day in range(1, 14):
        (out_dir / f"weekly-202608{day:02d}.json").write_text("{}\n", encoding="utf-8")
    unrelated = out_dir / "operator-note.json"
    unrelated.write_text("{}\n", encoding="utf-8")
    module.write_reports(report, out_dir)

    weekly = sorted(out_dir.glob("weekly-*.json"))
    assert len(weekly) == 12
    assert unrelated.exists()
    assert (out_dir / "latest.json").read_bytes() == (
        out_dir / "weekly-20260920.json"
    ).read_bytes()
    assert stat.S_IMODE((out_dir / "latest.json").stat().st_mode) == 0o600


def _apply_local_state_failure(
    failure: str, env: dict[str, str], receipt: Path, now: datetime
) -> None:
    if failure == "missing":
        receipt.unlink()
    elif failure == "malformed":
        receipt.write_text("{", encoding="utf-8")
    elif failure == "stale":
        stale = now.timestamp() - (8 * 24 * 60 * 60)
        os.utime(receipt, (stale, stale))
    elif failure == "blocked":
        document = json.loads(receipt.read_text(encoding="utf-8"))
        document["harnesses"]["claude"]["capabilities"][
            "manifest-workspace:mcp:context7"
        ] = "blocked"
        receipt.write_text(json.dumps(document), encoding="utf-8")
    elif failure == "pin-drift":
        (Path(env["OMP_AGENT_DIR"]) / "ui-expert.md").write_text(
            "drifted\n", encoding="utf-8"
        )
    elif failure == "native-missing":
        installation = Path(env["XDG_STATE_HOME"]) / "manifest/health/installation.json"
        document = json.loads(installation.read_text(encoding="utf-8"))
        del document["executables"]["claude"]
        installation.write_text(json.dumps(document), encoding="utf-8")


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("missing", "receipt_missing"),
        ("malformed", "receipt_malformed"),
        ("stale", "receipt_stale"),
        ("blocked", "capability_blocked"),
        ("pin-drift", "pin_hash_mismatch"),
        ("native-missing", "native_cli_missing"),
    ),
)
def test_weekly_health_report_degrades_on_unverifiable_local_state(
    report_bundle: Path,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    """Each local-state failure surfaces as its documented finding code."""
    module = load_runtime_module(
        _report_script(report_bundle),
        f"health_report_failure_{failure}_{tmp_path.name}",
    )
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    env, runtime_root, receipt = write_report_fixture(tmp_path, now)
    _apply_local_state_failure(failure, env, receipt, now)

    report = collect_report(module, env, runtime_root, now, HealthyReportRunner(module))

    assert report["status"] == "degraded"
    assert expected_code in {finding["code"] for finding in report["findings"]}


def test_weekly_health_report_degrades_safely_on_probe_timeout_and_hook_failure(
    report_bundle: Path, tmp_path: Path
) -> None:
    """Probe timeouts and unparseable hook output degrade without leaking text."""
    module = load_runtime_module(
        _report_script(report_bundle), f"health_report_probe_{tmp_path.name}"
    )
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    env, runtime_root, _receipt = write_report_fixture(tmp_path, now)
    healthy = HealthyReportRunner(module)

    def failed_runner(argv, timeout_seconds, environment):
        command = [str(item) for item in argv]
        if len(command) > 1 and Path(command[1]).name == "mcp_health.py":
            return module.CommandResult("timeout")
        if len(command) > 1 and Path(command[1]).name == "hook_smoke.py":
            return module.CommandResult(
                "complete",
                1,
                json.dumps(
                    {
                        "schema_version": 1,
                        "observed_at": "2026-09-20T12:00:00Z",
                        "status": "degraded",
                        "hashes": {},
                        "checks": [],
                        "findings": ["runtime_unavailable"],
                    }
                )
                + " https://secret.invalid/token",
            )
        return healthy(argv, timeout_seconds, environment)

    report = collect_report(module, env, runtime_root, now, failed_runner)

    encoded = json.dumps(report, sort_keys=True)
    assert report["status"] == "degraded"
    assert {"mcp_timeout", "hook_unparseable"} <= {
        finding["code"] for finding in report["findings"]
    }
    assert "secret.invalid" not in encoded


def test_health_report_bounded_runner_terminates_a_sleeping_process_group(
    report_bundle: Path, tmp_path: Path
) -> None:
    """run_bounded kills a process group that ignores its deadline."""
    module = load_runtime_module(
        _report_script(report_bundle),
        f"health_report_timeout_{tmp_path.name}",
    )
    started = time.monotonic()

    result = module.run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        0.2,
        isolated_env(tmp_path),
    )

    assert result.outcome == "timeout"
    assert time.monotonic() - started < 3


_NESTED_PROBE_SCRIPT = """\
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--timeout-seconds", type=float, required=True)
args, _unknown = parser.parse_known_args()
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    start_new_session=True,
)
Path(os.environ["NESTED_CHILD_PID_FILE"]).write_text(str(child.pid), encoding="utf-8")
try:
    child.wait(timeout=args.timeout_seconds)
except subprocess.TimeoutExpired:
    os.killpg(child.pid, signal.SIGKILL)
    child.wait(timeout=1)
print("{}")
raise SystemExit(1)
"""


def test_health_report_reserves_time_for_nested_mcp_probe_cleanup(
    report_bundle: Path, tmp_path: Path
) -> None:
    """The probe budget leaves headroom for the nested probe's own cleanup."""
    module = load_runtime_module(
        _report_script(report_bundle),
        f"health_report_nested_probe_{tmp_path.name}",
    )
    helper = tmp_path / "nested_probe.py"
    pid_file = tmp_path / "nested-child.pid"
    helper.write_text(_NESTED_PROBE_SCRIPT, encoding="utf-8")
    environment = isolated_env(tmp_path)
    environment["NESTED_CHILD_PID_FILE"] = str(pid_file)
    observation = module.Observation(
        "mcp:claude",
        "mcp",
        "claude",
        (
            sys.executable,
            str(helper),
            "--json",
            "--probe",
            "--harness",
            "claude",
            "--timeout-seconds",
            "20",
        ),
        2.5,
    )

    collect = sys.modules["health_report_collect"]
    result = collect._observation_result(
        observation,
        time.monotonic() + 2.5,
        time.monotonic,
        module.run_bounded,
        environment,
    )
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        assert result.outcome == "complete"
        assert result.returncode == 1
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        # Best-effort cleanup: a missing process is the expected outcome, so
        # ProcessLookupError here means the probe already cleaned up.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child_pid, 9)


def test_health_report_degrades_unobserved_receipt_backed_harness_version(
    report_bundle: Path, tmp_path: Path
) -> None:
    """A receipt-only harness with no observed version reports not_observed."""
    module = load_runtime_module(
        _report_script(report_bundle),
        f"health_report_unobserved_version_{tmp_path.name}",
    )
    now = datetime(2026, 9, 20, 12, tzinfo=UTC)
    env, runtime_root, receipt = write_report_fixture(tmp_path, now)
    receipt_document = json.loads(receipt.read_text(encoding="utf-8"))
    codex_record = json.loads(json.dumps(receipt_document["harnesses"]["claude"]))
    codex_record["harness"] = "codex"
    receipt_document["harnesses"]["codex"] = codex_record
    receipt.write_text(json.dumps(receipt_document), encoding="utf-8")
    timestamp = now.timestamp()
    os.utime(receipt, (timestamp, timestamp))
    healthy = HealthyReportRunner(module)

    def runner(argv: list[Any], timeout_seconds: float, environment: dict[str, str]):
        result = healthy(argv, timeout_seconds, environment)
        command = [str(item) for item in argv]
        if "reconcile" not in command:
            return result
        inventory = json.loads(result.stdout)
        inventory["harnesses"]["codex"] = healthy_harness_record()
        return module.CommandResult("complete", 0, json.dumps(inventory))

    report = collect_report(module, env, runtime_root, now, runner)

    assert report["status"] == "degraded"
    assert report["harnesses"]["codex"]["status"] == "degraded"
    assert report["harnesses"]["codex"]["version_status"] == "not_observed"
    assert {
        (finding["code"], finding.get("harness")) for finding in report["findings"]
    } >= {("version_not_observed", "codex")}
