"""Tests for tests/token_benchmark/workflows/runner.py.

Every test supplies a fake `invoke_fn`; none makes a network call, imports
a provider SDK, or touches a real container runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.workflows.fixtures import load_fixture
from tests.token_benchmark.workflows.records import validate_record
from tests.token_benchmark.workflows.runner import rotation_for_trial, run_trial

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "token_benchmark"
    / "workflows"
    / "fixtures"
)


def _fixture() -> dict:
    return load_fixture(FIXTURE_ROOT, "code-review")


def _passing_response() -> str:
    return json.dumps(
        {
            "findings": [
                {"id": "F1", "file": "counter.py", "line": 2, "category": "off_by_one"}
            ],
            "candidate_dispositions": [
                {"id": "C1", "decision": "refute", "reason": "no SQL involved"}
            ],
        }
    )


def _failing_response() -> str:
    return json.dumps({"findings": [], "candidate_dispositions": []})


def _completed(response_text, **overrides) -> dict:
    result = {
        "response_text": response_text,
        "input_tokens": 100,
        "output_tokens": 20,
        "latency_ms": 50,
        "model": "claude-sonnet-5[1m]",
        "effort": "provider-default",
        "tool_access": [],
        "status": "completed",
        "reason": None,
    }
    result.update(overrides)
    return result


class QueuedInvoke:
    """Fake invoke_fn returning one canned result per call, in order."""

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[dict] = []

    async def __call__(self, request, *, provider, model, timeout_s):
        self.calls.append(request)
        return self._results.pop(0)


async def _run(fake, condition="full"):
    return await run_trial(
        _fixture(),
        condition,
        invoke_fn=fake,
        executor=None,
        provider="claude",
        model="sonnet",
        trial_id="t-0",
        timeout_s=5,
    )


class TestFirstRepairSuccess:
    @pytest.mark.asyncio
    async def test_recovers_on_first_attempt(self):
        fake = QueuedInvoke(
            [_completed(_failing_response()), _completed(_passing_response())]
        )
        record = await _run(fake)
        validate_record(record)
        assert record["verification"] == "failed"
        assert record["repair"]["status"] == "recovered"
        assert len(record["repair"]["attempts"]) == 1

    @pytest.mark.asyncio
    async def test_repair_request_withholds_hidden_answers(self):
        fake = QueuedInvoke(
            [_completed(_failing_response()), _completed(_passing_response())]
        )
        await _run(fake)
        repair_request = fake.calls[1]
        assert repair_request["repair"]["prior_response"] == _failing_response()
        assert "hidden_cases" not in json.dumps(repair_request)


class TestTwoRepairFailures:
    @pytest.mark.asyncio
    async def test_exhausts_two_attempts_and_stays_unresolved(self):
        fake = QueuedInvoke(
            [
                _completed(_failing_response()),
                _completed(_failing_response()),
                _completed(_failing_response()),
            ]
        )
        record = await _run(fake)
        validate_record(record)
        assert record["repair"]["status"] == "unresolved"
        assert len(record["repair"]["attempts"]) == 2
        assert len(fake.calls) == 3  # initial call + exactly two repairs


class TestTimeout:
    @pytest.mark.asyncio
    async def test_initial_timeout_has_no_repair_attempts(self):
        fake = QueuedInvoke(
            [
                {
                    "response_text": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "latency_ms": 5000,
                    "model": "claude-sonnet-5[1m]",
                    "effort": "provider-default",
                    "tool_access": [],
                    "status": "timeout",
                    "reason": "exceeded 5s timeout",
                }
            ]
        )
        record = await _run(fake)
        validate_record(record)
        assert record["status"] == "timeout"
        assert record["verification"] == "unavailable"
        assert record["repair"] == {
            "status": "not_needed",
            "attempts": [],
            "latency_ms": 0,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
        }
        assert record["usage_unavailable_reason"] == "exceeded 5s timeout"


class TestMalformedResponse:
    @pytest.mark.asyncio
    async def test_malformed_response_is_failed_and_attempts_repair(self):
        fake = QueuedInvoke([_completed("not json"), _completed(_passing_response())])
        record = await _run(fake)
        validate_record(record)
        assert record["verification"] == "failed"
        assert record["constraint_results"] == {}
        assert record["repair"]["status"] == "recovered"


class TestUnknownUsage:
    @pytest.mark.asyncio
    async def test_missing_usage_on_initial_call_is_recorded_null_with_reason(self):
        fake = QueuedInvoke(
            [_completed(_passing_response(), input_tokens=None, output_tokens=None)]
        )
        record = await _run(fake)
        validate_record(record)
        assert record["input_tokens"] is None
        assert record["output_tokens"] is None
        assert record["usage_unavailable_reason"] is not None

    @pytest.mark.asyncio
    async def test_repair_aggregate_is_null_when_one_attempt_lacks_usage(self):
        fake = QueuedInvoke(
            [
                _completed(_failing_response()),
                _completed(_failing_response(), input_tokens=None, output_tokens=None),
                _completed(_passing_response()),
            ]
        )
        record = await _run(fake)
        validate_record(record)
        assert record["repair"]["status"] == "recovered"
        assert len(record["repair"]["attempts"]) == 2
        assert record["repair"]["input_tokens"] is None
        assert record["repair"]["output_tokens"] is None
        assert record["repair"]["attempts"][0]["input_tokens"] is None
        assert record["repair"]["attempts"][1]["input_tokens"] == 100


class TestRotation:
    def test_rotates_through_three_canonical_orderings(self):
        conditions = ("none", "slim", "full")
        assert rotation_for_trial(0, conditions) == ("none", "slim", "full")
        assert rotation_for_trial(1, conditions) == ("slim", "full", "none")
        assert rotation_for_trial(2, conditions) == ("full", "none", "slim")
        assert rotation_for_trial(3, conditions) == ("none", "slim", "full")

    def test_custom_subset_keeps_given_order(self):
        assert rotation_for_trial(1, ("slim",)) == ("slim",)
