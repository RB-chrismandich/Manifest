"""Load and deterministically resolve a bounded project-check registry."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator

from .debt import evaluate_findings
from .models import CheckSpec
from .preservation import load_invariants
from .receipt import is_number

VALID_GROUPS = frozenset({"lint", "test", "structure", "security", "package"})
VALID_PROFILES = frozenset({"quick", "full", "security", "release"})
_FIELDS = {
    "id",
    "group",
    "category",
    "argv",
    "cwd",
    "inputs",
    "dependencies",
    "timeout_seconds",
    "selection",
    "tool",
    "version",
    "honors_status_contract",
}

_SHELLS = frozenset(
    {
        "sh",
        "ash",
        "bash",
        "csh",
        "dash",
        "cmd",
        "fish",
        "ksh",
        "mksh",
        "pwsh",
        "powershell",
        "tcsh",
        "yash",
        "zsh",
    }
)
_WRAPPERS = frozenset({"env"})
_UNSUPPORTED_LAUNCHERS = frozenset({"nice", "nohup", "timeout", "busybox"})


def _executable_name(value: str) -> str:
    return PureWindowsPath(value).name.lower().removesuffix(".exe")


def _relative(value: str, label: str) -> None:
    if (
        Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or ".." in Path(value).parts
    ):
        raise ValueError(f"{label} must be candidate-relative")


def _policy_root(path: Path) -> Path:
    return path.parent.parent if path.parent.name == "config" else path.parent


def _policies(
    path: Path, document: dict[str, Any]
) -> tuple[dict[str, Any], tuple[str, ...]]:
    root = _policy_root(path)
    debt = evaluate_findings([], root / document["debt_baseline"])
    invariants = load_invariants(root / document["preservation"])
    return debt, invariants


def _document(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"registry is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("registry must be a JSON object")
    schema_path = _policy_root(path) / "schemas/project-checks.schema.json"
    if not schema_path.is_file():
        schema_path = Path(__file__).parents[3] / "schemas/project-checks.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"project checks schema is unavailable: {error}") from error
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise ValueError(f"registry schema validation failed: {errors[0].message}")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported registry schema_version")
    for key in ("debt_baseline", "preservation"):
        _relative(value[key], key)
    return payload, value


def _check(raw: Any, ids: set[str]) -> CheckSpec:
    if not isinstance(raw, dict) or _FIELDS - raw.keys():
        raise ValueError("check has missing required fields")
    name = raw.get("id")
    if not isinstance(name, str) or not name or name in ids:
        raise ValueError(f"duplicate or invalid check id: {name}")
    ids.add(name)
    if raw["group"] not in VALID_GROUPS:
        raise ValueError("invalid check group")
    argv = raw["argv"]
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        raise ValueError("check argv must be a non-empty string list")
    shell_indexes = [
        index
        for index, argument in enumerate(argv)
        if _executable_name(argument) in _SHELLS
    ]
    if shell_indexes:
        if any(
            option.startswith("-") and "c" in option.lstrip("-")
            for index in shell_indexes
            for option in argv[index + 1 :]
        ):
            raise ValueError("check cannot use shell string evaluation")
        raise ValueError("check cannot use shell interpreter")
    effective_index = _effective_command_index(argv)
    command = _executable_name(argv[effective_index])
    if command in _UNSUPPORTED_LAUNCHERS:
        raise ValueError("check launcher grammar is unsupported")
    _check_types(raw)
    body_paths = _check_body_paths(argv, effective_index)
    for body_path in body_paths:
        _relative(body_path, "check body path")
    if raw.get("honors_status_contract") and not _owned(body_paths):
        raise ValueError("honors_status_contract requires repo-owned check body")
    record = {key: raw[key] for key in CheckSpec.__dataclass_fields__ if key in raw}
    record.update(
        argv=tuple(argv),
        inputs=tuple(raw["inputs"]),
        dependencies=tuple(raw["dependencies"]),
    )
    return CheckSpec(**record)


def _check_types(raw: dict[str, Any]) -> None:
    values = (raw["cwd"], *raw["inputs"], *raw["dependencies"])
    if (
        not isinstance(raw["category"], str)
        or not raw["category"]
        or not isinstance(raw["selection"], str)
        or not raw["selection"]
        or not isinstance(raw["tool"], str)
        or not raw["tool"]
        or not isinstance(raw["version"], str)
        or not raw["version"]
        or not isinstance(raw["honors_status_contract"], bool)
        or not isinstance(raw["cwd"], str)
        or not all(isinstance(item, str) for item in values)
        or not is_number(raw["timeout_seconds"])
        or raw["timeout_seconds"] <= 0
    ):
        raise ValueError("check fields have invalid types")
    for value in values:
        _relative(value, "check path")


_ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")


def _effective_command_index(argv: list[str]) -> int:
    if _executable_name(argv[0]) not in _WRAPPERS:
        return 0
    index = 1
    while index < len(argv) and _ENV_ASSIGNMENT.fullmatch(argv[index]):
        index += 1
    if index == len(argv):
        raise ValueError("check argv wrapper has no command")
    if argv[index].startswith("-"):
        raise ValueError("check argv wrapper options are unsupported")
    if _executable_name(argv[index]) in _WRAPPERS:
        raise ValueError("check argv wrapper cannot wrap another wrapper")
    return index


def _check_body_paths(argv: list[str], command_index: int) -> tuple[str, ...]:
    return tuple(
        value
        for value in argv[command_index + 1 :]
        if not value.startswith("-") and ("/" in value or value.startswith("."))
    )


def _owned(body_paths: tuple[str, ...]) -> bool:
    return any(path.startswith("tools/project_checks/") for path in body_paths)


def _profiles(profiles: dict[str, Any], ids: set[str]) -> None:
    for profile in VALID_PROFILES:
        members = profiles.get(profile)
        if not isinstance(members, list) or not members:
            raise ValueError(f"profile {profile} must select checks")
        if len(members) != len(set(members)) or any(
            item not in ids for item in members
        ):
            raise ValueError(f"profile {profile} references unknown or duplicate check")


def load_registry(path: Path) -> dict[str, Any]:
    """Validate and load all executable registry declarations and policies."""
    payload, document = _document(path)
    ids: set[str] = set()
    checks = tuple(_check(raw, ids) for raw in document["checks"])
    _profiles(document["profiles"], ids)
    debt, invariants = _policies(path, document)
    return {
        "checks": checks,
        "profiles": document["profiles"],
        "path": path,
        "config_digest": hashlib.sha256(payload).hexdigest(),
        "debt_baseline": document["debt_baseline"],
        "preservation": document["preservation"],
        "debt": debt,
        "invariants": invariants,
    }


def resolve_checks(
    registry: dict[str, Any], profile: str, group: str | None = None
) -> tuple[CheckSpec, ...]:
    """Return the stable selected checks or reject unknown profile/group names."""
    if profile not in VALID_PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    if group is not None and group not in VALID_GROUPS:
        raise ValueError(f"unknown group: {group}")
    names = set(registry["profiles"][profile])
    return tuple(
        item
        for item in registry["checks"]
        if item.id in names and (group is None or item.group == group)
    )


def applicable_pending(*_args: Any, **_kwargs: Any) -> list[str]:
    """Reserved for future path filtering; Slice A has no implicit pending checks."""
    return []
