"""Pure helpers for reconciling checkpoint authority and evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from checkpoint_schema import authorization_errors


def git_changes(
    recorded: Mapping[str, object], current: Mapping[str, object]
) -> tuple[str, ...]:
    return tuple(
        key
        for key in ("path", "branch", "head", "dirty_tree")
        if recorded.get(key) != current.get(key)
    )


def ownership_changes(
    checkpoint: Mapping[str, Any],
    current_owners: Mapping[str, str],
    current_by_operation: Mapping[str, set[str]],
) -> tuple[str, ...]:
    recorded_owners = {
        str(operation["handle"]).strip(): str(operation["owner"]).strip()
        for operation in checkpoint["live_operations"]
    }
    changes = {
        handle
        for handle in recorded_owners.keys() | current_owners.keys()
        if recorded_owners.get(handle) != current_owners.get(handle)
    }
    for item in checkpoint["outstanding_operations"]:
        operation_name = str(item["operation"]).strip()
        owners = current_by_operation.get(operation_name, set())
        if owners != {str(item["owner"]).strip()}:
            changes.add(operation_name)
    return tuple(sorted(changes))


def authorization_state(
    checkpoint: Mapping[str, Any], current: Mapping[str, object] | None
) -> tuple[bool, bool]:
    invalid = current is None or bool(
        current is not None and authorization_errors(current)
    )
    changed = (
        current is not None
        and not invalid
        and dict(current) != checkpoint["authorization"]
    )
    empty = {
        "granted": [],
        "restrictions": [],
        "source": "",
        "observed_at": "",
    }
    missing = (current is None and checkpoint["authorization"] != empty) or (
        current is not None and invalid
    )
    return missing, changed


def stale_ci_evidence(
    checkpoint: Mapping[str, Any], current_repository: Mapping[str, object]
) -> tuple[str, ...]:
    targets = checkpoint["targets"]
    intended_target = targets.get("repository")
    intended_environment = targets.get("environment")
    return tuple(
        ref["reference"]
        for ref in checkpoint["completion"]["evidence_refs"]
        if ref["stage"] == "ci_verified"
        and (
            ref.get("commit_sha") != current_repository.get("head")
            or not intended_target
            or ref.get("target") != intended_target
            or not targets.get("branch")
            or ref.get("branch") != targets.get("branch")
            or not intended_environment
            or ref.get("environment") != intended_environment
        )
    )
