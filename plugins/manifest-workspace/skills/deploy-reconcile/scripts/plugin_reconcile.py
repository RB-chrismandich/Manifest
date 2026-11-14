#!/usr/bin/env python3
"""Compare installation receipts with independently observed native inventories.

Read-only. The receipt says what Manifest believes it installed; only a native
inspection (the coordinator's typed `native_inspection` contract, emitted by
`manifest-agent reconcile --json`) says what the harness actually has. Without
readable native evidence for a harness the result is `degraded` (unverified),
never `converged`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

EXPECTED_BUNDLES = {
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
}

# These states are emitted by the coordinator's typed native inventory.
_NATIVE_STATES = {"verified", "disabled", "missing", "inconsistent"}


def receipt_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state_home / "manifest/installation.json"


def _plugin_name(item: str) -> str:
    return item.split("@", 1)[0]


def _load_inspection(source: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        text = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
        document = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, f"native inspection unreadable: {error}"
    harnesses = document.get("harnesses") if isinstance(document, dict) else None
    if not isinstance(harnesses, dict):
        return None, "native inspection malformed: missing harnesses object"
    return harnesses, None


def _native_packages(record: object) -> tuple[dict[str, dict] | None, str | None]:
    """Validate one harness's native_inspection; return packages by name."""
    native = record.get("native_inspection") if isinstance(record, dict) else None
    if not isinstance(native, dict):
        return None, "no native inspection for harness"
    errors = native.get("inventory_errors")
    packages = native.get("packages")
    if (
        not isinstance(errors, list)
        or any(not isinstance(error, str) for error in errors)
        or not isinstance(packages, list)
    ):
        return None, "native inspection malformed"
    # Producer diagnostics include observed drift (missing/disabled/stale), not
    # just unreadable inventory. Preserve typed rows even when diagnostics exist.
    if errors and not packages:
        return None, "native inventory unreadable: " + "; ".join(errors)
    required_strings = ("package_id", "package_name", "status")
    nullable_strings = (
        "marketplace",
        "source_uri",
        "source_provenance",
        "version",
        "scope",
        "native_root",
        "install_path",
    )
    by_name: dict[str, dict] = {}
    for package in packages:
        if not isinstance(package, dict) or any(
            not isinstance(package.get(field), str) or not package[field]
            for field in required_strings
        ):
            return None, "native inspection package row malformed"
        if any(
            package.get(field) is not None and not isinstance(package.get(field), str)
            for field in nullable_strings
        ) or (
            package.get("enabled") is not None
            and not isinstance(package.get("enabled"), bool)
        ):
            return None, "native inspection package field malformed"
        if (
            package["status"] not in _NATIVE_STATES
            or package["package_name"] in by_name
        ):
            return None, "native inspection package row malformed"
        by_name[package["package_name"]] = package
    return by_name, "; ".join(errors) if errors else None


def _compare(harness: str, owned: set[str], native: dict[str, dict]) -> list[dict]:
    drift = []
    for name in sorted(
        owned | {n for n, p in native.items() if p["status"] != "missing"}
    ):
        package = native.get(name)
        status = package["status"] if package else "missing"
        if name in owned and status == "missing":
            reason = "missing: receipt owns it but native inventory lacks it"
        elif name in owned and status == "inconsistent":
            reason = "stale: native rows are inconsistent or stale"
        elif status == "disabled" or (package and package.get("enabled") is False):
            reason = "disabled: native package is installed but disabled"
        elif name not in owned:
            reason = "extra: native package is not owned by the receipt"
        else:
            continue
        drift.append({"capability": name, "harness": harness, "reason": reason})
    return drift


def _read_receipt(path: Path) -> tuple[Any, list[dict[str, str]]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except FileNotFoundError:
        return None, [
            {
                "capability": "installation-receipt",
                "harness": "all",
                "reason": "missing",
            }
        ]
    except (OSError, json.JSONDecodeError) as error:
        return None, [
            {
                "capability": "installation-receipt",
                "harness": "all",
                "reason": str(error),
            }
        ]


def _select_harnesses(
    receipt: object, harness_filter: tuple[str, ...]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    harnesses = receipt.get("harnesses", {}) if isinstance(receipt, dict) else {}
    if not isinstance(harnesses, dict):
        harnesses = {}
    drift = []
    if harness_filter:
        harnesses = {
            key: value for key, value in harnesses.items() if key in harness_filter
        }
        for name in sorted(set(harness_filter) - set(harnesses)):
            drift.append(
                {
                    "capability": "installation-receipt",
                    "harness": name,
                    "reason": "harness absent from receipt",
                }
            )
    return harnesses, drift


def _native_component_drift(
    harness: str, inspection: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    drift = []
    unverified = []
    components = inspection.get("components")
    if not isinstance(components, list):
        return drift, [
            {"harness": harness, "reason": "native components absent or malformed"}
        ]
    for component in components:
        valid_row = (
            isinstance(component, dict)
            and isinstance(component.get("identifier"), str)
            and bool(component["identifier"])
            and isinstance(component.get("kind"), str)
            and bool(component["kind"])
            and isinstance(component.get("status"), str)
            and bool(component["status"])
            and isinstance(component.get("provenance"), str)
            and bool(component["provenance"])
            and "resolved_path" in component
            and (
                component["resolved_path"] is None
                or isinstance(component["resolved_path"], str)
            )
        )
        if not valid_row:
            unverified.append(
                {"harness": harness, "reason": "native component row malformed"}
            )
            continue
        state = component["status"]
        capability = f"{component['kind']}:{component['identifier']}"
        if state in {"unresolved", "missing", "disabled", "stale", "inconsistent"}:
            drift.append(
                {"harness": harness, "capability": capability, "reason": state}
            )
        elif (
            state != "resolved"
            or component["provenance"] == "not-observed"
            or not component["resolved_path"]
        ):
            unverified.append({"harness": harness, "reason": f"{capability}: {state}"})
    return drift, unverified


def _reconcile_harness(
    harness: str,
    record: object,
    native_report: dict[str, Any] | None,
    inspection_error: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    drift = []
    unverified = []
    plugins = (
        record.get("plugins", record.get("plugin_ids", []))
        if isinstance(record, dict)
        else []
    )
    installed = {_plugin_name(item) for item in plugins if isinstance(item, str)}
    missing = sorted(EXPECTED_BUNDLES - installed)
    if missing:
        drift.append(
            {
                "capability": ",".join(missing),
                "harness": harness,
                "reason": "domain plugins absent from receipt inventory",
            }
        )
    if native_report is None:
        return drift, [{"harness": harness, "reason": inspection_error}]
    native, error = _native_packages(native_report.get(harness))
    if native is None:
        return drift, [{"harness": harness, "reason": str(error)}]
    drift.extend(_compare(harness, installed, native))
    if error:
        if native_report[harness].get("state") == "DRIFTED":
            drift.append(
                {
                    "harness": harness,
                    "capability": "native-inventory",
                    "reason": error,
                }
            )
        else:
            unverified.append({"harness": harness, "reason": error})
    inspection = native_report[harness]["native_inspection"]
    component_drift, component_unverified = _native_component_drift(harness, inspection)
    drift.extend(component_drift)
    unverified.extend(component_unverified)
    if inspection.get("activation") != "verified":
        unverified.append(
            {"harness": harness, "reason": "native activation not verified"}
        )
    return drift, unverified


def reconcile(
    inspection_source: str | None = None, harness_filter: tuple[str, ...] = ()
) -> dict:
    path = receipt_path()
    receipt, drift = _read_receipt(path)
    harnesses, filter_drift = _select_harnesses(receipt, harness_filter)
    drift.extend(filter_drift)
    native_report, inspection_error = (
        _load_inspection(inspection_source)
        if inspection_source is not None
        else (None, "no native inspection supplied (--native-inspection)")
    )
    unverified = []
    for harness, record in sorted(harnesses.items()):
        harness_drift, harness_unverified = _reconcile_harness(
            str(harness), record, native_report, str(inspection_error)
        )
        drift.extend(harness_drift)
        unverified.extend(harness_unverified)
    if receipt is not None and not harnesses and not harness_filter:
        unverified.append({"harness": "all", "reason": "receipt records no harnesses"})
    status = "degraded" if unverified else "drift" if drift else "converged"
    return {
        "drift": drift,
        "receipt": str(path),
        "repair_required": bool(drift),
        "status": status,
        "unverified": unverified,
        "verified": not unverified and receipt is not None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--native-inspection",
        metavar="PATH",
        help="coordinator `reconcile --json` report ('-' for stdin)",
    )
    parser.add_argument(
        "--harness",
        action="append",
        default=[],
        help="limit comparison to this receipt harness; repeatable",
    )
    args = parser.parse_args(argv)
    report = reconcile(args.native_inspection, tuple(args.harness))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"plugin reconcile: {report['status']}")
        for item in report["drift"]:
            print(f"{item['harness']}: {item['capability']} - {item['reason']}")
        for item in report["unverified"]:
            print(f"{item['harness']}: unverified - {item['reason']}")
        if report["repair_required"]:
            print(
                "repair required; use the installer documentation for an explicit uvx repair"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
