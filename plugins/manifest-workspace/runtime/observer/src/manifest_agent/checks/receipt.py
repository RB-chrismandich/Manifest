"""Receipt shape validation shared by local consumers."""

from __future__ import annotations

from typing import Any


def is_integer(value: Any) -> bool:
    """Return whether JSON value is an integer rather than a boolean."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    """Return whether JSON value is numeric rather than a boolean."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _result_errors(results: list[Any]) -> list[str]:
    errors: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            errors.append("receipt results must be objects")
            continue
        if not isinstance(result.get("id"), str) or not result["id"]:
            errors.append("receipt result id must be a nonempty string")
        status = result.get("status")
        if not isinstance(status, str) or status not in {"PASS", "FAIL", "BLOCKED"}:
            errors.append("receipt result status is invalid")
        if result.get("returncode") is not None and not is_integer(
            result.get("returncode")
        ):
            errors.append("receipt result returncode must be an integer or null")
        if not is_number(result.get("duration_seconds", 0)):
            errors.append("receipt result duration_seconds must be numeric")
        findings = result.get("findings", [])
        if not isinstance(findings, list) or not all(
            isinstance(finding, dict)
            and set(finding) == {"id"}
            and isinstance(finding.get("id"), str)
            and finding["id"]
            for finding in findings
        ):
            errors.append("receipt result findings are invalid")
    return errors


def validate_receipt(receipt: Any) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt must be an object"]
    required = {
        "schema_version": (is_integer, "integer"),
        "profile": (lambda value: isinstance(value, str), "str"),
        "group": (lambda value: isinstance(value, str), "str"),
        "head_sha": (lambda value: isinstance(value, str), "str"),
        "base_sha": (lambda value: isinstance(value, str), "str"),
        "candidate_digest": (lambda value: isinstance(value, str), "str"),
        "config_digest": (lambda value: isinstance(value, str), "str"),
        "required_ids": (lambda value: isinstance(value, list), "list"),
        "results": (lambda value: isinstance(value, list), "list"),
        "status": (lambda value: isinstance(value, str), "str"),
        "run_attempt": (is_integer, "integer"),
        "artifact_id": (lambda value: isinstance(value, str), "str"),
    }
    errors = [
        f"receipt {name} must be a nonempty {kind}"
        for name, (predicate, kind) in required.items()
        if not predicate(receipt.get(name))
        or (kind == "str" and not receipt[name])
        or (kind == "list" and not receipt[name])
    ]
    if is_integer(receipt.get("schema_version")) and receipt["schema_version"] != 1:
        errors.append("receipt has unsupported schema_version")
    status = receipt.get("status")
    if isinstance(status, str) and status not in {"PASS", "FAIL", "BLOCKED"}:
        errors.append("receipt has invalid status")
    required_ids = receipt.get("required_ids")
    if isinstance(required_ids, list):
        valid_ids = all(isinstance(item, str) and item for item in required_ids)
        if not valid_ids or len(required_ids) != len(set(required_ids)):
            errors.append("receipt required_ids must be unique nonempty strings")
    results = receipt.get("results")
    if isinstance(results, list):
        errors.extend(_result_errors(results))
    return errors
