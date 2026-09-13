"""Fail-closed aggregation for producer receipts."""

from __future__ import annotations

from typing import Any

from .models import CheckResult
from .preservation import evaluate_invariants
from .receipt import is_integer, validate_receipt
from .registry import resolve_checks


def _context_errors(context: Any) -> list[str]:
    if not isinstance(context, dict):
        return ["aggregation context must be an object"]
    required = {
        "tested_sha": str,
        "base_sha": str,
        "candidate_digest": str,
        "config_digest": str,
        "run_attempt": is_integer,
        "producer_jobs": list,
    }
    errors: list[str] = []
    for name, predicate in required.items():
        value = context.get(name)
        valid = (
            is_integer(value)
            if predicate is is_integer
            else isinstance(value, predicate)
        )
        if not valid or (predicate in {str, list} and not value):
            kind = "integer" if predicate is is_integer else predicate.__name__
            errors.append(f"context {name} must be a nonempty {kind}")
    return errors


def _jobs(context: dict[str, Any], diagnostics: list[str]) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for job in context.get("producer_jobs", []):
        if (
            not isinstance(job, dict)
            or not isinstance(job.get("group"), str)
            or not is_integer(job.get("run_attempt"))
        ):
            diagnostics.append("producer job is invalid")
            continue
        group = job["group"]
        if group in jobs:
            diagnostics.append(f"duplicate producer job for {group}")
        jobs[group] = job
    return jobs


def _receipt_errors(
    receipt: dict[str, Any],
    context: dict[str, Any],
    profile: str,
    jobs: dict[str, dict[str, Any]],
) -> list[str]:
    errors = validate_receipt(receipt)
    if errors:
        return errors
    if receipt.get("profile") != profile:
        errors.append("receipt profile mismatch")
    for field, context_field in (
        ("head_sha", "tested_sha"),
        ("base_sha", "base_sha"),
        ("candidate_digest", "candidate_digest"),
        ("config_digest", "config_digest"),
        ("run_attempt", "run_attempt"),
    ):
        if receipt.get(field) != context.get(context_field):
            errors.append(f"receipt {field} mismatch")
    if receipt.get("status") != "PASS":
        errors.append("receipt status is not PASS")
    job = jobs.get(receipt.get("group"))
    if not job:
        errors.append("receipt group has no producer")
    elif (
        job.get("conclusion") != "success"
        or job.get("artifact_id") != receipt.get("artifact_id")
        or job.get("run_attempt") != context.get("run_attempt")
    ):
        errors.append("receipt does not match successful producer")
    return errors


def aggregate_results(
    registry: dict[str, Any],
    profile: str,
    receipts: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Return PASS only for complete, current, uniquely owned producer results."""
    checks = resolve_checks(registry, profile)
    expected = {item.id: item.group for item in checks}
    diagnostics = _context_errors(context)
    if diagnostics:
        return {
            "schema_version": 1,
            "profile": profile,
            "status": "BLOCKED",
            "diagnostics": diagnostics,
        }
    jobs = _jobs(context, diagnostics)
    if context["config_digest"] != registry["config_digest"]:
        diagnostics.append("context config_digest mismatch")
    if set(jobs) != set(expected.values()):
        diagnostics.append("producer groups do not match selected checks")
    seen_checks: set[str] = set()
    seen_groups: set[str] = set()
    seen_artifacts: set[str] = set()
    valid_receipts: list[dict[str, Any]] = []
    for receipt in receipts:
        receipt_errors = _receipt_errors(receipt, context, profile, jobs)
        diagnostics.extend(receipt_errors)
        if receipt_errors:
            continue
        valid_receipts.append(receipt)
        _verify_receipt_checks(
            receipt, expected, seen_checks, seen_groups, seen_artifacts, diagnostics
        )
    policy_results = [
        CheckResult(
            result["id"],
            result.get("status", ""),
            result.get("returncode") if is_integer(result.get("returncode")) else None,
            0,
        )
        for receipt in valid_receipts
        for result in receipt["results"]
        if isinstance(result.get("id"), str)
    ]
    diagnostics.extend(
        evaluate_invariants(registry["invariants"], checks, policy_results)
    )
    if seen_checks != set(expected):
        diagnostics.append("receipts do not cover exactly the selected checks")
    return {
        "schema_version": 1,
        "profile": profile,
        "status": "BLOCKED" if diagnostics else "PASS",
        "diagnostics": diagnostics,
    }


def _verify_receipt_checks(
    receipt: dict[str, Any],
    expected: dict[str, str],
    seen_checks: set[str],
    seen_groups: set[str],
    seen_artifacts: set[str],
    diagnostics: list[str],
) -> None:
    if not isinstance(receipt, dict):
        return
    group = receipt.get("group")
    if group in seen_groups:
        diagnostics.append(f"duplicate receipt for group {group}")
    seen_groups.add(group)
    artifact = receipt.get("artifact_id")
    if artifact in seen_artifacts:
        diagnostics.append(f"duplicate receipt artifact {artifact}")
    seen_artifacts.add(artifact)
    expected_ids = {name for name, owner in expected.items() if owner == group}
    result_ids = set()
    for result in receipt.get("results", []):
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            diagnostics.append("receipt result is invalid")
            continue
        check_id = result["id"]
        result_ids.add(check_id)
        if check_id in seen_checks:
            diagnostics.append(f"duplicate receipt for {check_id}")
        seen_checks.add(check_id)
        if expected.get(check_id) != group:
            diagnostics.append(f"result {check_id} does not belong to producer {group}")
        if result.get("status") != "PASS":
            diagnostics.append(f"non-passing check {check_id}")
    if (
        result_ids != expected_ids
        or set(receipt.get("required_ids", [])) != expected_ids
    ):
        diagnostics.append(f"receipt checks do not match group {group}")
