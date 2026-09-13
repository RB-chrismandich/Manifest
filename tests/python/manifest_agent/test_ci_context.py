"""Contracts for the read-only current-run CI context collector."""

from __future__ import annotations

import pytest

from manifest_agent.checks.aggregate import aggregate_results
from manifest_agent.checks.registry import load_registry
from tests.python.manifest_agent.test_shared_checks_slice_a import receipt, registry
from tools.project_checks.ci_context import CIContextBlockedError, collect_ci_context

ENV = {
    "GITHUB_REPOSITORY": "acme/example",
    "GITHUB_WORKFLOW": "ci.yml",
    "GITHUB_RUN_ID": "1001",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_SHA": "a" * 40,
    "MANIFEST_BASE_SHA": "b" * 40,
}
IDENTITY = {
    "candidate_digest": "candidate-digest",
    "config_digest": "config-digest",
}


def _fake_fetch(jobs):
    def fetch(repository: str, run_id: str, run_attempt: str):
        assert repository == ENV["GITHUB_REPOSITORY"]
        assert run_id == ENV["GITHUB_RUN_ID"]
        assert run_attempt == ENV["GITHUB_RUN_ATTEMPT"]
        return jobs

    return fetch


def test_collect_ci_context_stamps_the_current_run_attempt_onto_every_job():
    jobs = [
        {"group": "lint", "job_id": "1", "conclusion": "success", "artifact_id": "a"},
        {
            "group": "test",
            "job_id": "2",
            "conclusion": "success",
            "artifact_id": "b",
            # A provider response that already carries a (stale) run_attempt
            # must not leak through: the current run's own attempt wins.
            "run_attempt": 999,
        },
    ]

    result = collect_ci_context(ENV, _fake_fetch(jobs), **IDENTITY)

    assert result == {
        "repository": "acme/example",
        "workflow": "ci.yml",
        "run_id": "1001",
        "run_attempt": 1,
        "tested_sha": "a" * 40,
        "base_sha": "b" * 40,
        "candidate_digest": "candidate-digest",
        "config_digest": "config-digest",
        "producer_jobs": [
            {
                "group": "lint",
                "job_id": "1",
                "conclusion": "success",
                "artifact_id": "a",
                "run_attempt": 1,
            },
            {
                "group": "test",
                "job_id": "2",
                "conclusion": "success",
                "artifact_id": "b",
                "run_attempt": 1,
            },
        ],
    }


@pytest.mark.parametrize(
    "missing",
    ["GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ATTEMPT", "MANIFEST_BASE_SHA"],
)
def test_collect_ci_context_missing_env_is_blocked(missing):
    env = {key: value for key, value in ENV.items() if key != missing}

    with pytest.raises(CIContextBlockedError, match=missing):
        collect_ci_context(env, _fake_fetch([]), **IDENTITY)


def test_collect_ci_context_fetch_failure_is_blocked():
    def failing_fetch(repository: str, run_id: str, run_attempt: str):
        raise RuntimeError("api unavailable")

    with pytest.raises(CIContextBlockedError, match="api unavailable"):
        collect_ci_context(ENV, failing_fetch, **IDENTITY)


def test_collect_ci_context_non_list_fetch_result_is_blocked():
    def bad_fetch(repository: str, run_id: str, run_attempt: str):
        return {"not": "a list"}

    with pytest.raises(CIContextBlockedError, match="non-list"):
        collect_ci_context(ENV, bad_fetch, **IDENTITY)


def test_collect_ci_context_output_is_accepted_by_aggregate_results(tmp_path):
    """A live context can be consumed by the current aggregate contract."""
    loaded = load_registry(registry(tmp_path / "checks.json"))
    digest = loaded["config_digest"]
    jobs = [
        {
            "group": "test",
            "job_id": "1",
            "conclusion": "success",
            "artifact_id": "artifact",
        }
    ]
    context = collect_ci_context(
        ENV,
        _fake_fetch(jobs),
        candidate_digest="candidate",
        config_digest=digest,
    )
    item = receipt()
    item["head_sha"] = ENV["GITHUB_SHA"]
    item["base_sha"] = ENV["MANIFEST_BASE_SHA"]
    item["config_digest"] = digest

    report = aggregate_results(loaded, "full", [item], context)

    assert report["status"] == "PASS", report["diagnostics"]
