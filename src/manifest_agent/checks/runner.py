"""Execute declared checks and produce self-contained receipts."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .candidate_integrity import identity_error
from .debt import evaluate_findings
from .models import Candidate, CheckResult, CheckSpec
from .preservation import evaluate_invariants, load_invariants
from .process import run_argv
from .registry import resolve_checks
from .status import executed_status


def _policy_errors(
    registry: dict[str, Any], candidate: Candidate
) -> tuple[list[str], tuple[str, ...]]:
    errors: list[str] = []
    try:
        debt = evaluate_findings([], candidate.root / registry["debt_baseline"])
        if debt["status"] != "PASS":
            errors.append("debt baseline contains newly introduced findings")
    except ValueError as error:
        errors.append(str(error))
    try:
        invariants = load_invariants(candidate.root / registry["preservation"])
    except ValueError as error:
        errors.append(str(error))
        invariants = ()
    return errors, invariants


def _findings(stdout: str) -> tuple[dict[str, str], ...]:
    if not stdout.strip():
        return ()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ()
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if findings is None:
        return ()
    if not isinstance(findings, list) or not all(
        isinstance(item, dict)
        and set(item) == {"id"}
        and isinstance(item["id"], str)
        and item["id"]
        for item in findings
    ):
        raise ValueError("check findings must be objects with a nonempty id")
    if len({item["id"] for item in findings}) != len(findings):
        raise ValueError("check findings contain duplicate ids")
    return tuple({"id": item["id"]} for item in findings)


def execute_check(
    check: CheckSpec, candidate: Candidate, env: dict[str, str]
) -> CheckResult:
    try:
        completed = run_argv(
            check.argv, candidate.root / check.cwd, env, check.timeout_seconds
        )
        if completed.timed_out:
            return CheckResult(
                check.id,
                "BLOCKED",
                None,
                completed.duration_seconds,
                "check timed out",
                check.inputs,
            )
        code = completed.returncode
        assert code is not None
        status = executed_status(code, check.honors_status_contract)
        findings = _findings(completed.stdout)
        diagnostic = (
            ""
            if status == "PASS"
            else "repo-owned status contract blocked"
            if code == 3 and check.honors_status_contract
            else (completed.stderr or completed.stdout)[-4096:]
            if code in {2, 3} or not check.honors_status_contract
            else f"status contract violation: exit {code}"
        )
    except (OSError, ValueError) as error:
        code, status, diagnostic, findings, completed = (
            None,
            "BLOCKED",
            str(error),
            (),
            None,
        )
    return CheckResult(
        check.id,
        status,
        code,
        completed.duration_seconds if completed else 0,
        diagnostic,
        check.inputs,
        findings,
    )


def _blocked_report(
    profile: str, group: str | None, diagnostics: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile": profile,
        "group": group,
        "status": "BLOCKED",
        "diagnostics": diagnostics,
        "results": [],
    }


def run_profile(
    registry: dict[str, Any],
    profile: str,
    group: str | None,
    candidate: Candidate,
    env: dict[str, str],
) -> dict[str, Any]:
    checks = resolve_checks(registry, profile, group)
    if not checks:
        return _blocked_report(profile, group, ["selection has no executable checks"])
    policy_errors, invariants = _policy_errors(registry, candidate)
    before = identity_error(candidate)
    if before:
        policy_errors.append(before)
    if policy_errors:
        return _blocked_report(profile, group, policy_errors)
    results = []
    for check in checks:
        results.append(execute_check(check, candidate, env))
        mutation = identity_error(candidate)
        if mutation:
            policy_errors.append(mutation)
            break
    policy_errors.extend(evaluate_invariants(invariants, checks, results))
    debt_diagnostics: list[str] = []
    debt = evaluate_findings(
        [finding for result in results for finding in result.findings],
        candidate.root / registry["debt_baseline"],
    )
    if debt["status"] != "PASS":
        debt_diagnostics.append(f"new debt findings: {', '.join(debt['new_findings'])}")
    statuses = {result.status for result in results}
    status = (
        "BLOCKED"
        if policy_errors or "BLOCKED" in statuses
        else "FAIL"
        if debt_diagnostics or "FAIL" in statuses
        else "PASS"
    )
    return {
        "schema_version": 1,
        "profile": profile,
        "group": group,
        "head_sha": candidate.head_sha,
        "base_sha": candidate.base_sha,
        "candidate_digest": candidate.digest,
        "config_digest": registry["config_digest"],
        "required_ids": [check.id for check in checks],
        "results": [asdict(result) for result in results],
        "status": status,
        "run_attempt": 1,
        "artifact_id": "local",
        "diagnostics": [*policy_errors, *debt_diagnostics],
    }
