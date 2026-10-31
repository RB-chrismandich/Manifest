"""Keep checkout-controlled CI execution on disposable hosted runners."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
GROUPS = ("structure", "lint", "test", "security", "package")


def test_every_ci_runner_is_hosted_including_dispatch_matrix() -> None:
    """PR source and manually selected refs must never reach a reused host."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name, job in workflow["jobs"].items():
        runners = [job["runs-on"]]
        if runners == ["${{ fromJSON(matrix.runner) }}"]:
            runners = [
                json.loads(row["runner"])
                for row in job["strategy"]["matrix"]["include"]
            ]
        assert runners
        for runner in runners:
            assert runner in ("ubuntu-latest", "ubuntu-24.04-arm"), (
                f"{name}: checkout-controlled code must use a hosted VM, got {runner!r}"
            )


@pytest.mark.parametrize("group", GROUPS)
def test_shared_checks_keep_arm64_and_run_for_prs(group: str) -> None:
    """Isolation must preserve PR checks, architecture pins, and aggregation."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # BaseLoader preserves GitHub's `on` key instead of YAML 1.1 boolean coercion.
    triggers = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert set(triggers["on"]) == {"pull_request", "push", "workflow_dispatch"}
    job_name = f"shadow-checks-{group}"
    job = workflow["jobs"][job_name]
    assert job["runs-on"] == "ubuntu-24.04-arm"
    assert "if" not in job
    assert job_name in workflow["jobs"]["checks-aggregate-full"]["needs"]
    for step in job["steps"]:
        command = step.get("run", "")
        if "manifest provision" in command:
            assert "--platform linux-arm64" in command
