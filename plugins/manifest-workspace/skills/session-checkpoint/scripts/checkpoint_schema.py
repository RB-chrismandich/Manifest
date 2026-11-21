"""Validate and migrate persisted checkpoint schema records."""

from __future__ import annotations

from collections.abc import Mapping

CHECKPOINT_SCHEMA_VERSION = 2
LEGACY_CHECKPOINT_SCHEMA_VERSION = 1
COMPLETION_STAGES = (
    "implemented",
    "committed",
    "pushed",
    "ci_verified",
    "merged",
    "deployed",
    "live_validated",
)
_STAGE_OUTCOMES = frozenset({"unknown", "not_required"})
_CHECKPOINT_FIELDS = {
    "source_session_id": str,
    "original_goal": str,
    "constraints": list,
    "decisions": list,
    "repository": dict,
    "completed_work": list,
    "remaining_work": list,
    "verification_evidence": list,
    "unresolved_uncertainty": list,
    "next_action": str,
    "live_operations": list,
    "continuation_goal": str,
}
_OPTIONAL_CHECKPOINT_FIELDS = {
    "requested_endpoint",
    "authorization",
    "targets",
    "artifacts",
    "verified_facts",
    "outstanding_operations",
    "completion",
    "blockers",
}


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _exact_keys(
    value: Mapping[str, object], required: set[str], optional: set[str], label: str
) -> list[str]:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    errors = (
        [f"{label} missing fields: {', '.join(sorted(missing))}"] if missing else []
    )
    if unknown:
        errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    return errors


def _repository_errors(repository: Mapping[str, object]) -> list[str]:
    errors = [
        f"repository.{field} must be a non-empty string"
        for field in ("path", "branch", "head")
        if not _nonempty_str(repository.get(field))
    ]
    dirty_tree = repository.get("dirty_tree")
    if not isinstance(dirty_tree, list):
        errors.append("repository.dirty_tree is required")
    elif any(not _nonempty_str(entry) for entry in dirty_tree):
        errors.append("repository.dirty_tree entries must be non-empty strings")
    return errors


def _record_errors(records: object, label: str, fields: tuple[str, ...]) -> list[str]:
    if not isinstance(records, list):
        return []
    required = (
        ", ".join(fields[:-1]) + f", and {fields[-1]}"
        if len(fields) > 2
        else " and ".join(fields)
    )
    return [
        f"{label}[{index}] requires {required}"
        for index, item in enumerate(records)
        if not isinstance(item, dict)
        or any(not _nonempty_str(item.get(field)) for field in fields)
    ]


def defaults_for_extended_fields(checkpoint: Mapping[str, object]) -> dict[str, object]:
    """Add safe v1 migration defaults without implying authorization or success."""
    result = dict(checkpoint)
    result.setdefault("requested_endpoint", "")
    result.setdefault(
        "authorization",
        {"granted": [], "restrictions": [], "source": "", "observed_at": ""},
    )
    result.setdefault("targets", {})
    result.setdefault("artifacts", [])
    result.setdefault("verified_facts", [])
    result.setdefault("outstanding_operations", [])
    result.setdefault(
        "completion",
        {
            "stages": dict.fromkeys(COMPLETION_STAGES, "not_required"),
            "evidence_refs": [],
        },
    )
    result.setdefault("blockers", [])
    return result


def _base_errors(checkpoint: Mapping[str, object], legacy: bool) -> list[str]:
    errors = _exact_keys(
        checkpoint,
        set(_CHECKPOINT_FIELDS),
        set() if legacy else _OPTIONAL_CHECKPOINT_FIELDS,
        "checkpoint",
    )
    for field, expected_type in _CHECKPOINT_FIELDS.items():
        value = checkpoint.get(field)
        if not isinstance(value, expected_type) or (
            expected_type is str and not value.strip()
        ):
            errors.append(f"{field} must be a non-empty {expected_type.__name__}")
    repository = checkpoint.get("repository")
    if isinstance(repository, dict):
        errors.extend(
            _exact_keys(
                repository,
                {"path", "branch", "head", "dirty_tree"},
                set(),
                "repository",
            )
        )
        errors.extend(_repository_errors(repository))
    errors.extend(
        _record_errors(
            checkpoint.get("verification_evidence"),
            "verification_evidence",
            ("command", "outcome", "evidence"),
        )
    )
    errors.extend(
        _record_errors(
            checkpoint.get("live_operations"),
            "live_operations",
            ("owner", "handle", "status", "obligation"),
        )
    )
    return errors


def authorization_errors(authorization: object) -> list[str]:
    """Validate an authorization snapshot without accepting unproven grants."""
    errors: list[str] = []
    auth_keys = {"granted", "restrictions", "source", "observed_at"}
    if not isinstance(authorization, dict):
        return ["authorization must be an object"]
    errors.extend(_exact_keys(authorization, auth_keys, set(), "authorization"))
    for field in ("granted", "restrictions"):
        values = authorization.get(field)
        if not isinstance(values, list) or any(
            not _nonempty_str(item) for item in values
        ):
            errors.append(f"authorization.{field} must be a list of non-empty strings")
    populated = any(authorization.get(field) for field in ("granted", "restrictions"))
    for field in ("source", "observed_at"):
        value = authorization.get(field)
        if not isinstance(value, str):
            errors.append(f"authorization.{field} must be a string")
        elif populated and not _nonempty_str(value):
            errors.append(
                f"authorization.{field} is required for populated authorization"
            )
    return errors


def _authorization_errors(checkpoint: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    endpoint = checkpoint.get("requested_endpoint")
    if not isinstance(endpoint, str):
        errors.append("requested_endpoint must be a string")
    errors.extend(authorization_errors(checkpoint.get("authorization")))
    return errors


def _target_errors(checkpoint: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    targets = checkpoint.get("targets")
    allowed = {"repository", "branch", "mr", "pipeline", "job", "environment"}
    if not isinstance(targets, dict):
        errors.append("targets must be an object")
    else:
        errors.extend(_exact_keys(targets, set(), allowed, "targets"))
        if any(not _nonempty_str(value) for value in targets.values()):
            errors.append("targets values must be non-empty strings")
    for field in ("artifacts", "blockers"):
        value = checkpoint.get(field)
        if not isinstance(value, list) or any(
            not _nonempty_str(item) for item in value
        ):
            errors.append(f"{field} must be a list of non-empty strings")
    return errors


def _structured_record_error(
    field: str, index: int, record: object, fields: tuple[str, ...]
) -> list[str]:
    if not isinstance(record, dict):
        return [f"{field}[{index}] must be an object"]
    errors = _exact_keys(record, set(fields), set(), f"{field}[{index}]")
    for name in fields:
        item = record.get(name)
        if name == "blockers":
            if not isinstance(item, list) or any(
                not _nonempty_str(value) for value in item
            ):
                errors.append(
                    f"{field}[{index}].blockers must be a list of non-empty strings"
                )
        elif not _nonempty_str(item):
            errors.append(f"{field}[{index}].{name} must be a non-empty string")
    return errors


def _structured_record_errors(checkpoint: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    fields_by_type = (
        ("verified_facts", ("fact", "provenance", "observed_at")),
        ("outstanding_operations", ("operation", "owner", "blockers", "next_step")),
    )
    for field, fields in fields_by_type:
        records = checkpoint.get(field)
        if not isinstance(records, list):
            errors.append(f"{field} must be a list")
            continue
        for index, record in enumerate(records):
            errors.extend(_structured_record_error(field, index, record, fields))
    return errors


def _stage_errors(stages: object) -> list[str]:
    if not isinstance(stages, dict):
        return ["completion.stages must be an object"]
    errors = _exact_keys(stages, set(COMPLETION_STAGES), set(), "completion.stages")
    if any(
        not (
            type(value) is bool or (isinstance(value, str) and value in _STAGE_OUTCOMES)
        )
        for value in stages.values()
    ):
        errors.append(
            "completion stage values must be booleans, unknown, or not_required"
        )
    return errors


def _evidence_errors(refs: object) -> list[str]:
    if not isinstance(refs, list):
        return ["completion.evidence_refs must be a list"]
    errors: list[str] = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"completion.evidence_refs[{index}] must be an object")
            continue
        errors.extend(
            _exact_keys(
                ref,
                {"stage", "reference"},
                {"commit_sha", "target", "branch", "environment"},
                f"completion.evidence_refs[{index}]",
            )
        )
        if ref.get("stage") not in COMPLETION_STAGES:
            errors.append(f"completion.evidence_refs[{index}].stage is invalid")
        if not _nonempty_str(ref.get("reference")):
            errors.append(
                f"completion.evidence_refs[{index}].reference must be non-empty"
            )
        if ref.get("stage") == "ci_verified" and not _nonempty_str(
            ref.get("commit_sha")
        ):
            errors.append(
                f"completion.evidence_refs[{index}] CI evidence requires commit_sha"
            )
        elif "commit_sha" in ref and not _nonempty_str(ref["commit_sha"]):
            errors.append(
                f"completion.evidence_refs[{index}].commit_sha must be non-empty"
            )
        for field in ("target", "branch", "environment"):
            if field in ref and not _nonempty_str(ref[field]):
                errors.append(
                    f"completion.evidence_refs[{index}].{field} must be non-empty"
                )

    return errors


def _completion_errors(checkpoint: Mapping[str, object]) -> list[str]:
    completion = checkpoint.get("completion")
    if not isinstance(completion, dict):
        return ["completion must be an object"]
    errors = _exact_keys(completion, {"stages", "evidence_refs"}, set(), "completion")
    stages = completion.get("stages")
    refs = completion.get("evidence_refs")
    errors.extend(_stage_errors(stages))
    errors.extend(_evidence_errors(refs))
    if (
        isinstance(stages, dict)
        and stages.get("ci_verified") is True
        and isinstance(refs, list)
        and not any(
            isinstance(ref, dict) and ref.get("stage") == "ci_verified" for ref in refs
        )
    ):
        errors.append("completion.ci_verified requires commit-bound evidence")
    return errors


def validate_checkpoint(
    checkpoint: Mapping[str, object], *, legacy: bool = False
) -> list[str]:
    """Return precise schema violations for a checkpoint record."""
    errors = _base_errors(checkpoint, legacy)
    if legacy:
        return errors
    errors.extend(_authorization_errors(checkpoint))
    errors.extend(_target_errors(checkpoint))
    errors.extend(_structured_record_errors(checkpoint))
    errors.extend(_completion_errors(checkpoint))
    return errors
