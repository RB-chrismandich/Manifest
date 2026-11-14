#!/usr/bin/env python3
"""Read and validate native harness observation evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

NATIVE_COMMAND = "manifest observe-native --json"
_NATIVE_REQUIRED_FIELDS = (
    "state",
    "verified",
    "converged",
    "version",
    "installed_plugin_ids",
    "capabilities",
    "components",
    "errors",
    "warnings",
)
_NATIVE_STATES = {"READY", "DEGRADED", "BLOCKED", "DRIFTED"}


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _native_record_validation_errors(record: dict[str, Any]) -> list[str]:
    missing = (field for field in _NATIVE_REQUIRED_FIELDS if field not in record)
    errors = [f"missing required field: {field}" for field in missing]
    state = record.get("state")
    if "state" in record and (
        not isinstance(state, str) or state not in _NATIVE_STATES
    ):
        errors.append("state must be READY, DEGRADED, BLOCKED, or DRIFTED")
    for field in ("verified", "converged"):
        if field in record and not isinstance(record[field], bool):
            errors.append(f"{field} must be a boolean")
    if state == "BLOCKED" and (
        record.get("verified") is not False or record.get("converged") is not False
    ):
        errors.append("BLOCKED state flags are inconsistent")
    if state == "DRIFTED" and record.get("converged") is True:
        errors.append("DRIFTED state cannot be converged")
    version = record.get("version")
    if version == "" or (version is not None and not isinstance(version, str)):
        errors.append("version must be a non-empty string or null")
    plugin_ids = record.get("installed_plugin_ids")
    if "installed_plugin_ids" in record and (
        not isinstance(plugin_ids, list)
        or not all(isinstance(item, str) and item for item in plugin_ids)
    ):
        errors.append("installed_plugin_ids must be a list of non-empty strings")
    capabilities = record.get("capabilities")
    if "capabilities" in record and (
        not isinstance(capabilities, dict)
        or not all(
            isinstance(key, str) and key and isinstance(value, str) and value
            for key, value in capabilities.items()
        )
    ):
        errors.append("capabilities must map non-empty strings to non-empty strings")
    components = record.get("components")
    if "components" in record and (
        not isinstance(components, dict)
        or not all(
            isinstance(key, str)
            and key
            and isinstance(items, list)
            and all(isinstance(item, str) and item for item in items)
            for key, items in components.items()
        )
    ):
        errors.append("components must map non-empty strings to string lists")
    for field in ("errors", "warnings"):
        if field in record and not _is_string_list(record[field]):
            errors.append(f"{field} must be a list of strings")
    return errors


def _observed(record: object) -> dict[str, Any]:
    """Preserve native evidence and report producer-contract violations."""
    if not isinstance(record, dict):
        return {"present": False}
    version = record.get("version")
    plugin_ids = record.get("installed_plugin_ids")
    components = record.get("components")
    errors = record.get("errors")
    warnings = record.get("warnings")
    return {
        "present": True,
        "state": record.get("state"),
        "verified": record.get("verified") is True,
        "converged": record.get("converged") is True,
        "version": version if isinstance(version, str) else None,
        "installed_plugin_ids": sorted(
            item for item in plugin_ids if isinstance(item, str)
        )
        if isinstance(plugin_ids, list)
        else [],
        "components": components if isinstance(components, dict) else {},
        "errors": [item for item in errors if isinstance(item, str)]
        if isinstance(errors, list)
        else [],
        "warnings": [item for item in warnings if isinstance(item, str)]
        if isinstance(warnings, list)
        else [],
        "validation_errors": _native_record_validation_errors(record),
    }


def _validate_native_envelope(document: object) -> tuple[dict | None, str | None]:
    if (
        not isinstance(document, dict)
        or document.get("operation") != "reconcile"
        or not isinstance(document.get("harnesses"), dict)
    ):
        return None, f"native evidence is not a `{NATIVE_COMMAND}` report"
    if not _is_string_list(document.get("errors", [])):
        return None, "native evidence errors must be a list of strings"
    return document, None


def load_native_evidence(source: str) -> tuple[dict | None, str | None]:
    """Read an explicitly supplied saved reconcile report."""
    try:
        text = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
        document = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, f"native evidence is unreadable: {error}"
    return _validate_native_envelope(document)


def _repository_root() -> Path | None:
    """Find a checkout only when this script is actually inside one."""
    for candidate in Path(__file__).resolve().parents:
        if (
            (candidate / ".git").exists()
            and (candidate / "pyproject.toml").is_file()
            and (candidate / "plugins").is_dir()
        ):
            return candidate
    return None


def observe_native() -> tuple[dict | None, str | None]:
    executable = shutil.which("manifest")
    if executable is None:
        return None, "native observation CLI `manifest` is unavailable"
    command = [executable, "observe-native", "--json"]
    repository = _repository_root()
    if repository is not None:
        command.extend(("--source-root", str(repository)))
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit status {completed.returncode}"
            return None, f"native observation CLI failed: {detail}"
        return _validate_native_envelope(json.loads(completed.stdout))
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        return None, f"native state observation failed: {type(error).__name__}: {error}"
