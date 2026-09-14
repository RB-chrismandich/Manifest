"""Apply-mode branch-protection CLI reconciliation tests.

These cases use the real fake-``gh`` subprocess fixture and helpers from the
baseline CLI module. They cover precondition refusal and write confirmation;
dry-run and read-only outcomes remain in ``test_protection_cli.py``.
"""

from __future__ import annotations

import json
from typing import Any

from manifest_agent import protection
from tests.python.manifest_agent.test_protection_cli import (
    _cli_args,
    _cli_env,
    _config_dict,
    _log_entries,
    _mutated,
    _run_cli,
    _setup_target,
    _stage_get,
    _write_response,
    _write_workflow,
    env,
)


def test_apply_refused_when_aggregate_has_continue_on_error(
    env: dict[str, Any],
) -> None:
    """--apply refuses and issues no write when the aggregate job masks failure."""
    _, proposed = _setup_target(env, aggregate_continue_on_error=True)
    _stage_get(env, 1, _mutated(proposed, enforce_admins=False))

    result = _run_cli(_cli_args(env, "--apply", "--json"), _cli_env(env))
    assert result.returncode == 3
    body = json.loads(result.stdout.decode())
    assert body["status"] == "blocked"
    unmet = [item for item in body["preconditions"] if not item["met"]]
    assert any("continue-on-error" in item["reason"] for item in unmet)

    entries = _log_entries(env)
    assert all("PUT" not in item["argv"] for item in entries)


def test_apply_refused_when_aggregate_step_has_continue_on_error(
    env: dict[str, Any],
) -> None:
    """--apply rejects failure masking on the aggregate verdict step."""
    config = _config_dict()
    env["config_path"].write_text(json.dumps(config), encoding="utf-8")
    _write_workflow(
        env["workflow_path"],
        aggregate_step_continue_on_error=True,
    )
    workflow_jobs = protection.parse_workflow(env["workflow_path"])
    contexts = protection.resolve_contexts(config, workflow_jobs)
    proposed = protection.build_payload(config, contexts)
    _stage_get(env, 1, _mutated(proposed, enforce_admins=False))

    result = _run_cli(_cli_args(env, "--apply", "--json"), _cli_env(env))
    assert result.returncode == 3
    body = json.loads(result.stdout.decode())
    assert body["status"] == "blocked"
    assert any(
        "continue-on-error" in item["reason"]
        for item in body["preconditions"]
        if not item["met"]
    )
    assert all("PUT" not in item["argv"] for item in _log_entries(env))


def test_apply_issues_one_put_with_exact_payload_then_reads_back(
    env: dict[str, Any],
) -> None:
    """A successful --apply PUTs the exact payload then confirms it with a GET."""
    _, proposed = _setup_target(env, aggregate_continue_on_error=False)
    _stage_get(env, 1, _mutated(proposed, enforce_admins=False))
    _write_response(env, "put-1", stdout="{}")
    _stage_get(env, 2, proposed)

    result = _run_cli(_cli_args(env, "--apply", "--json"), _cli_env(env))
    assert result.returncode == 0
    body = json.loads(result.stdout.decode())
    assert body["status"] == "applied"

    entries = _log_entries(env)
    assert len(entries) == 3
    methods = ["PUT" if "PUT" in entry["argv"] else "GET" for entry in entries]
    assert methods == ["GET", "PUT", "GET"]

    put_entry = entries[1]
    assert "--input" in put_entry["argv"]
    assert json.loads(put_entry["stdin"]) == proposed


def test_apply_residual_drift_after_put_exits_two(env: dict[str, Any]) -> None:
    """A post-PUT reread that still drifts returns exit 2 rather than trusting PUT."""
    _, proposed = _setup_target(env, aggregate_continue_on_error=False)
    old_live = _mutated(proposed, enforce_admins=False)
    _stage_get(env, 1, old_live)
    _write_response(env, "put-1", stdout="{}")
    _stage_get(env, 2, old_live)

    result = _run_cli(_cli_args(env, "--apply", "--json"), _cli_env(env))
    assert result.returncode == 2
    body = json.loads(result.stdout.decode())
    assert body["status"] == "residual_drift"
    assert body["diff"]
