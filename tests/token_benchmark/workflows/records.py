"""Version-2 workflow benchmark result record schema and boundary validation.

A record is a plain dictionary (see `runner.run_trial`); this module only
enforces the required fields, their types, and the three status enums so a
malformed record can never reach `tests/token_benchmark/results/*.jsonl`.
"""

from __future__ import annotations

SCHEMA_VERSION = 2
SUITE = "workflow"
CONDITIONS = frozenset({"none", "slim", "full"})

TRIAL_STATUSES = frozenset({"completed", "unsupported", "error", "timeout"})
VERIFICATION_STATUSES = frozenset({"passed", "failed", "unavailable"})
REPAIR_STATUSES = frozenset({"not_needed", "recovered", "unresolved", "unavailable"})

_RECORD_FIELDS = {
    "schema_version": int,
    "suite": str,
    "condition": str,
    "fixture_id": str,
    "fixture_hash": str,
    "context_hash": str,
    "source_revision": str,
    "trial_id": str,
    "provider": str,
    "model": (str, type(None)),
    "effort": (str, type(None)),
    "tool_access": list,
    "status": str,
    "verification": str,
    "constraint_results": dict,
    "latency_ms": (int, type(None)),
    "input_tokens": (int, type(None)),
    "output_tokens": (int, type(None)),
    "cost_usd": (float, int, type(None)),
    "usage_unavailable_reason": (str, type(None)),
    "repair": dict,
}

_REPAIR_FIELDS = {
    "status": str,
    "attempts": list,
    "latency_ms": (int, type(None)),
    "input_tokens": (int, type(None)),
    "output_tokens": (int, type(None)),
    "cost_usd": (float, int, type(None)),
}

_ATTEMPT_FIELDS = {
    "attempt_id": str,
    "status": str,
    "verification": (str, type(None)),
    "input_tokens": (int, type(None)),
    "output_tokens": (int, type(None)),
    "latency_ms": (int, type(None)),
    "reason": (str, type(None)),
}


def _validate_fields(payload: dict, spec: dict, label: str) -> None:
    for name, types in spec.items():
        if name not in payload:
            raise ValueError(f"{label} missing required field: {name!r}")
        if not isinstance(payload[name], types):
            raise ValueError(f"{label} field {name!r} has wrong type")


def _validate_enum(value: str, allowed: frozenset, label: str) -> None:
    if value not in allowed:
        raise ValueError(f"unknown {label}: {value!r}")


def _validate_attempt(attempt: dict) -> None:
    _validate_fields(attempt, _ATTEMPT_FIELDS, "repair attempt")
    _validate_enum(attempt["status"], TRIAL_STATUSES, "repair attempt status")
    if attempt["verification"] is not None:
        _validate_enum(
            attempt["verification"],
            VERIFICATION_STATUSES,
            "repair attempt verification",
        )


def _validate_repair(repair: dict) -> None:
    _validate_fields(repair, _REPAIR_FIELDS, "repair")
    _validate_enum(repair["status"], REPAIR_STATUSES, "repair.status")
    if repair["status"] == "not_needed" and repair["attempts"]:
        raise ValueError("repair.status=not_needed must have no attempts")
    if repair["status"] in ("recovered", "unresolved") and not repair["attempts"]:
        raise ValueError(
            f"repair.status={repair['status']!r} requires at least one attempt"
        )
    for attempt in repair["attempts"]:
        _validate_attempt(attempt)
    _validate_repair_usage(repair)


def _validate_repair_usage(repair: dict) -> None:
    attempts = repair["attempts"]
    any_missing = any(
        a["input_tokens"] is None or a["output_tokens"] is None for a in attempts
    )
    aggregate_known = (
        repair["input_tokens"] is not None or repair["output_tokens"] is not None
    )
    if attempts and any_missing and aggregate_known:
        raise ValueError(
            "repair aggregate usage must be null when any attempt usage is unknown"
        )


def _validate_usage(record: dict) -> None:
    usage_missing = record["input_tokens"] is None or record["output_tokens"] is None
    if usage_missing and not record["usage_unavailable_reason"]:
        raise ValueError("usage_unavailable_reason required when usage is null")


def validate_record(record: dict) -> None:
    """Validate a version-2 workflow record's required fields, types, and
    enums, including the nested `repair` sub-object. Raises `ValueError` on
    the first violation found; never mutates `record`."""
    _validate_fields(record, _RECORD_FIELDS, "record")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {record['schema_version']!r}")
    if record["suite"] != SUITE:
        raise ValueError(f"unsupported suite: {record['suite']!r}")
    if record["condition"] not in CONDITIONS:
        raise ValueError(f"unknown condition: {record['condition']!r}")
    _validate_enum(record["status"], TRIAL_STATUSES, "status")
    _validate_enum(record["verification"], VERIFICATION_STATUSES, "verification")
    _validate_repair(record["repair"])
    _validate_usage(record)
