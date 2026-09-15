"""Tests for tests/token_benchmark/workflows/records.py."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.workflows.records import validate_record

BASE_RECORD = {
    "schema_version": 2,
    "suite": "workflow",
    "condition": "none",
    "fixture_id": "implementation",
    "fixture_hash": "a" * 64,
    "context_hash": "b" * 64,
    "source_revision": "78f7f4ab431d35f5c355fee1ce45e78b854e1007",
    "trial_id": "implementation-none-run-0",
    "provider": "claude",
    "model": "claude-sonnet-5[1m]",
    "effort": "provider-default",
    "tool_access": [],
    "status": "completed",
    "verification": "failed",
    "constraint_results": {"required_findings": False},
    "latency_ms": 100,
    "input_tokens": 500,
    "output_tokens": 40,
    "cost_usd": 0.0016,
    "usage_unavailable_reason": None,
    "repair": {
        "status": "unresolved",
        "attempts": [
            {
                "attempt_id": "repair-1",
                "status": "completed",
                "verification": "failed",
                "input_tokens": 520,
                "output_tokens": 30,
                "latency_ms": 90,
                "reason": None,
            }
        ],
        "latency_ms": 90,
        "input_tokens": 520,
        "output_tokens": 30,
        "cost_usd": 0.001,
    },
}


class TestValidRecord:
    def test_well_formed_record_passes(self):
        validate_record(deepcopy(BASE_RECORD))


class TestMissingOrWrongTypeFields:
    def test_missing_required_field_raises(self):
        record = deepcopy(BASE_RECORD)
        del record["fixture_hash"]
        with pytest.raises(ValueError, match="fixture_hash"):
            validate_record(record)

    def test_wrong_type_raises(self):
        record = deepcopy(BASE_RECORD)
        record["tool_access"] = "none"
        with pytest.raises(ValueError, match="tool_access"):
            validate_record(record)


class TestEnums:
    def test_unknown_status_raises(self):
        record = deepcopy(BASE_RECORD)
        record["status"] = "bogus"
        with pytest.raises(ValueError, match="status"):
            validate_record(record)

    def test_unknown_verification_raises(self):
        record = deepcopy(BASE_RECORD)
        record["verification"] = "bogus"
        with pytest.raises(ValueError, match="verification"):
            validate_record(record)

    def test_unknown_repair_status_raises(self):
        record = deepcopy(BASE_RECORD)
        record["repair"]["status"] = "bogus"
        with pytest.raises(ValueError, match=r"repair\.status"):
            validate_record(record)

    def test_unknown_condition_raises(self):
        record = deepcopy(BASE_RECORD)
        record["condition"] = "before"
        with pytest.raises(ValueError, match="condition"):
            validate_record(record)


class TestRepairInvariants:
    def test_not_needed_with_attempts_raises(self):
        record = deepcopy(BASE_RECORD)
        record["repair"]["status"] = "not_needed"
        with pytest.raises(ValueError, match="not_needed"):
            validate_record(record)

    def test_recovered_with_no_attempts_raises(self):
        record = deepcopy(BASE_RECORD)
        record["repair"]["status"] = "recovered"
        record["repair"]["attempts"] = []
        with pytest.raises(ValueError, match="recovered"):
            validate_record(record)

    def test_not_needed_with_zero_attempts_and_zero_time_is_valid(self):
        record = deepcopy(BASE_RECORD)
        record["verification"] = "passed"
        record["repair"] = {
            "status": "not_needed",
            "attempts": [],
            "latency_ms": 0,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
        }
        validate_record(record)

    def test_zero_latency_on_a_real_attempt_does_not_block_recovered(self):
        """Zero observed repair time is valid only when no repair call
        occurred; a genuinely fast (0ms) recorded attempt must not be
        rejected just because its latency happens to be zero."""
        record = deepcopy(BASE_RECORD)
        record["repair"]["status"] = "recovered"
        record["repair"]["latency_ms"] = 0
        record["repair"]["attempts"][0]["latency_ms"] = 0
        record["repair"]["attempts"][0]["verification"] = "passed"
        validate_record(record)


class TestUsageConsistency:
    def test_null_usage_without_reason_raises(self):
        record = deepcopy(BASE_RECORD)
        record["input_tokens"] = None
        record["output_tokens"] = None
        record["usage_unavailable_reason"] = None
        with pytest.raises(ValueError, match="usage_unavailable_reason"):
            validate_record(record)

    def test_null_usage_with_reason_is_valid(self):
        record = deepcopy(BASE_RECORD)
        record["input_tokens"] = None
        record["output_tokens"] = None
        record["usage_unavailable_reason"] = "not reported"
        validate_record(record)

    def test_repair_aggregate_usage_must_be_null_when_any_attempt_unknown(self):
        record = deepcopy(BASE_RECORD)
        record["repair"]["attempts"].append(
            {
                "attempt_id": "repair-2",
                "status": "timeout",
                "verification": None,
                "input_tokens": None,
                "output_tokens": None,
                "latency_ms": 120,
                "reason": "exceeded timeout",
            }
        )
        with pytest.raises(ValueError, match="repair aggregate usage"):
            validate_record(record)

    def test_repair_aggregate_usage_null_when_any_attempt_unknown_is_valid(self):
        record = deepcopy(BASE_RECORD)
        record["repair"]["attempts"].append(
            {
                "attempt_id": "repair-2",
                "status": "timeout",
                "verification": None,
                "input_tokens": None,
                "output_tokens": None,
                "latency_ms": 120,
                "reason": "exceeded timeout",
            }
        )
        record["repair"]["input_tokens"] = None
        record["repair"]["output_tokens"] = None
        record["repair"]["latency_ms"] = 210
        validate_record(record)
