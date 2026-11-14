#!/usr/bin/env python3
"""Inspect installation receipts and installed harness inventories read-only.
Report receipt and native observations separately; missing native evidence is
unverified. Authentication and operation-level capability are never tested."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# runpy.run_path does not add the script directory to sys.path.
try:
    from env_check_native import (
        NATIVE_COMMAND,
        _observed,
        load_native_evidence,
        observe_native,
    )
except ModuleNotFoundError as error:
    if error.name != "env_check_native":
        raise
    _native_path = Path(__file__).with_name("env_check_native.py")
    _native_spec = importlib.util.spec_from_file_location(
        "env_check_native", _native_path
    )
    if _native_spec is None or _native_spec.loader is None:
        raise ImportError(
            f"cannot load native evidence helper at {_native_path}"
        ) from error
    _native_module = importlib.util.module_from_spec(_native_spec)
    _native_spec.loader.exec_module(_native_module)
    NATIVE_COMMAND = _native_module.NATIVE_COMMAND
    _observed = _native_module._observed
    load_native_evidence = _native_module.load_native_evidence
    observe_native = _native_module.observe_native

HARNESSES = {
    "antigravity": "agy",
    "claude": "claude",
    "codex": "codex",
    "cursor": "cursor-agent",
    "devin": "devin",
    "omp": "omp",
}
NOT_TESTED = "not_tested"


def receipt_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state_home / "manifest/installation.json"


def load_receipt(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "installation receipt is absent"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, f"installation receipt is unreadable: {error}"
    if not isinstance(document, dict):
        return None, "installation receipt is not a JSON object"
    return document, None


def _valid_receipt_identity(document: object) -> bool:
    """Validate exact top-level keys, versions, and source/archive hashes."""
    import re

    full_commit = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
    sha256 = re.compile(r"^[0-9a-fA-F]{64}$")
    receipt_keys = {
        "schema_version",
        "coordinator_version",
        "release_version",
        "source_commit",
        "source_dirty",
        "archive_sha256",
        "bundle_checksums",
        "selected_optional",
        "harnesses",
        "migration_backup",
    }
    if not isinstance(document, dict) or set(document) != receipt_keys:
        return False
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        return False
    if not all(
        isinstance(document[key], str)
        for key in (
            "coordinator_version",
            "release_version",
            "source_commit",
            "archive_sha256",
        )
    ):
        return False
    if not full_commit.fullmatch(document["source_commit"]) or not sha256.fullmatch(
        document["archive_sha256"]
    ):
        return False
    if not isinstance(document["source_dirty"], bool):
        return False
    checksums = document["bundle_checksums"]
    if not isinstance(checksums, dict) or any(
        not isinstance(k, str)
        or not k
        or not isinstance(v, str)
        or not sha256.fullmatch(v)
        for k, v in checksums.items()
    ):
        return False
    if not isinstance(document["selected_optional"], list) or not all(
        isinstance(item, str) for item in document["selected_optional"]
    ):
        return False
    return document["migration_backup"] is None or isinstance(
        document["migration_backup"], str
    )


def _valid_owned_entries(entries: object, entry_keys: set[str]) -> bool:
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != entry_keys
            or not all(
                isinstance(entry[key], str)
                for key in ("kind", "identifier", "ownership_marker")
            )
            or (
                entry["target_path"] is not None
                and not isinstance(entry["target_path"], str)
            )
            or (
                entry["previous_checksum"] is not None
                and not isinstance(entry["previous_checksum"], str)
            )
        ):
            return False
    return True


def _valid_harnesses(document: dict) -> bool:
    harness_names = {"claude", "codex", "cursor", "antigravity", "devin", "omp"}
    harness_keys = {
        "harness",
        "adapter_version",
        "native_version",
        "plugin_ids",
        "owned_entries",
        "capabilities",
        "verified",
        "errors",
    }
    entry_keys = {
        "kind",
        "identifier",
        "ownership_marker",
        "target_path",
        "previous_checksum",
    }
    harnesses = document["harnesses"]
    if not isinstance(harnesses, dict) or set(harnesses) - harness_names:
        return False
    for name, record in harnesses.items():
        if (
            not isinstance(name, str)
            or not isinstance(record, dict)
            or set(record) != harness_keys
        ):
            return False
        if (
            record["harness"] != name
            or not all(
                isinstance(record[key], str)
                for key in ("adapter_version", "native_version")
            )
            or not isinstance(record["verified"], bool)
            or not isinstance(record["plugin_ids"], list)
            or not all(isinstance(item, str) for item in record["plugin_ids"])
            or not isinstance(record["errors"], list)
            or not all(isinstance(item, str) for item in record["errors"])
            or not isinstance(record["capabilities"], dict)
            or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in record["capabilities"].items()
            )
            or (not record["verified"] and not record["errors"])
            or not _valid_owned_entries(record["owned_entries"], entry_keys)
        ):
            return False
    return True


def _valid_receipt(document: object) -> bool:
    """Mirror the coordinator state decoder and its non-cryptographic checks."""
    return _valid_receipt_identity(document) and _valid_harnesses(document)


def evaluate_receipt(path: Path) -> dict[str, Any]:
    """Return receipt claims, or an explicit reason the receipt is unusable."""
    document, error = load_receipt(path)
    summary: dict[str, Any] = {
        "path": str(path),
        "present": path.exists(),
        "valid": False,
        "selected": [],
        "claims": {},
        "problems": [],
    }
    if error is not None:
        summary["problems"].append(error)
        return summary
    if not _valid_receipt(document):
        summary["problems"].append(
            "installation receipt does not match the coordinator schema"
        )
        return summary
    assert document is not None
    harnesses = document["harnesses"]
    if not harnesses:
        summary["problems"].append("installation receipt selects no harness")
        return summary
    summary["valid"] = True
    summary["selected"] = sorted(harnesses)
    summary["claims"] = {
        name: {
            "verified": record["verified"],
            "native_version": record["native_version"],
            "plugin_ids": sorted(record["plugin_ids"]),
            "errors": list(record["errors"]),
        }
        for name, record in sorted(harnesses.items())
    }
    return summary


def compare(receipt: dict[str, Any], native: dict | None) -> dict[str, Any]:
    """Compare receipt claims with native observations per selected harness."""
    native_harnesses = native["harnesses"] if native is not None else {}
    harnesses: dict[str, Any] = {}
    drift: list[dict[str, str]] = []
    for name in receipt["selected"]:
        claim = receipt["claims"][name]
        reasons: list[str] = []
        if not claim["verified"]:
            reasons.append("receipt records an unverified installation")
        observed: dict[str, Any] | str = "not_observed"
        if native is not None:
            observed = _observed(native_harnesses.get(name))
            if not observed["present"]:
                reasons.append("selected harness absent from native observation")
            else:
                reasons.extend(observed["validation_errors"])
                if not observed["verified"]:
                    reasons.append(
                        f"native inspection not verified (state {observed['state']})"
                    )
                if not observed["converged"]:
                    reasons.append("native inspection did not converge")
                    reasons.extend(
                        f"native harness error: {error}" for error in observed["errors"]
                    )
                if observed["version"] is None:
                    reasons.append("native version not observed")
                elif observed["version"] != claim["native_version"]:
                    reasons.append("native version differs from receipt")
                missing = sorted(
                    set(claim["plugin_ids"]) - set(observed["installed_plugin_ids"])
                )
                if missing:
                    reasons.append(
                        "receipt plugins not observed natively: " + ",".join(missing)
                    )
        harnesses[name] = {
            "receipt": claim,
            "observed": observed,
            "authentication": NOT_TESTED,
            "operation_capability": NOT_TESTED,
        }
        drift.extend({"harness": name, "reason": reason} for reason in reasons)
    unselected_observed = sorted(set(native_harnesses) - set(receipt["selected"]))
    native_errors = (
        [item for item in native.get("errors", []) if isinstance(item, str)]
        if native is not None
        else []
    )
    drift.extend({"harness": "all", "reason": f"native: {e}"} for e in native_errors)
    return {
        "harnesses": harnesses,
        "drift": drift,
        "native_observed": native is not None,
        "unselected_observed": unselected_observed,
    }


def assess(native_source: str | None = None) -> dict[str, Any]:
    """Shared receipt+native assessment used by env-check and deploy-reconcile."""
    receipt = evaluate_receipt(receipt_path())
    if native_source:
        native, native_error = load_native_evidence(native_source)
    elif receipt["valid"]:
        native, native_error = observe_native()
    else:
        native, native_error = None, None
    comparison = compare(receipt, native)
    problems = list(receipt["problems"])
    if native_error is not None:
        problems.append(native_error)
    if problems or comparison["drift"]:
        status = "degraded"
    elif not comparison["native_observed"]:
        status = "unverified"
    else:
        status = "ok"
    return {
        "receipt": receipt,
        "comparison": comparison,
        "problems": problems,
        "status": status,
    }


def inspect(native_source: str | None = None) -> dict:
    assessment = assess(native_source)
    receipt = assessment["receipt"]
    comparison = assessment["comparison"]
    selected = set(receipt["selected"])
    inventories = {
        harness: {
            "binary": binary,
            "available": shutil.which(binary) is not None,
            "selected": harness in selected,
        }
        for harness, binary in HARNESSES.items()
    }
    warnings = list(assessment["problems"])
    warnings.extend(
        f"{item['harness']}: {item['reason']}" for item in comparison["drift"]
    )
    warnings.extend(
        f"{name}: selected but executable `{inventories[name]['binary']}` not on PATH"
        for name in sorted(selected)
        if name in inventories and not inventories[name]["available"]
    )
    if not comparison["native_observed"]:
        warnings.append(
            f"native state not observed; pass `--native-evidence` with `{NATIVE_COMMAND}` output"
        )
    status = assessment["status"]
    if status == "ok" and any(
        not inventories[name]["available"] for name in selected if name in inventories
    ):
        status = "degraded"
    return {
        "authentication": NOT_TESTED,
        "harnesses": comparison["harnesses"],
        "inventories": inventories,
        "native_observed": comparison["native_observed"],
        "unselected_observed": comparison["unselected_observed"],
        "receipt": {
            "path": receipt["path"],
            "present": receipt["present"],
            "valid": receipt["valid"],
            "selected": receipt["selected"],
        },
        "status": status,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--native-evidence",
        metavar="PATH",
        help=f"saved `{NATIVE_COMMAND}` output, or - for stdin",
    )
    args = parser.parse_args(argv)
    report = inspect(args.native_evidence)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"workspace environment: {report['status']}")
        for harness, inventory in report["inventories"].items():
            state = "available" if inventory["available"] else "missing"
            role = "selected" if inventory["selected"] else "not selected"
            print(f"{harness}: {state} ({inventory['binary']}, {role})")
        print("authentication: not tested")
        for warning in report["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
