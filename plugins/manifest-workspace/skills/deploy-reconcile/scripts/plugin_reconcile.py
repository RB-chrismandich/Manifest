#!/usr/bin/env python3
"""Compare installation receipts with the packaged domain catalog read-only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

EXPECTED_BUNDLES = {
    "manifest-code-quality",
    "manifest-docs",
    "manifest-forge",
    "manifest-graphify",
    "manifest-ops",
    "manifest-security",
    "manifest-spec-planning",
    "manifest-workspace",
    "stitch-design",
}


def receipt_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state_home / "manifest/installation.json"


def reconcile() -> dict:
    path = receipt_path()
    drift: list[dict[str, str]] = []
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        receipt = None
        drift.append(
            {
                "capability": "installation-receipt",
                "harness": "all",
                "reason": "missing",
            }
        )
    except (OSError, json.JSONDecodeError) as error:
        receipt = None
        drift.append(
            {
                "capability": "installation-receipt",
                "harness": "all",
                "reason": str(error),
            }
        )
    harnesses = receipt.get("harnesses", {}) if isinstance(receipt, dict) else {}
    if isinstance(harnesses, dict):
        for harness, record in sorted(harnesses.items()):
            plugins = (
                record.get("plugins", record.get("plugin_ids", []))
                if isinstance(record, dict)
                else []
            )
            installed = {
                str(item).split("@", 1)[0] for item in plugins if isinstance(item, str)
            }
            missing = sorted(EXPECTED_BUNDLES - installed)
            if missing:
                drift.append(
                    {
                        "capability": ",".join(missing),
                        "harness": str(harness),
                        "reason": "domain plugins absent from receipt inventory",
                    }
                )
    return {
        "drift": drift,
        "receipt": str(path),
        "repair_required": bool(drift),
        "status": "drift" if drift else "converged",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = reconcile()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"plugin reconcile: {report['status']}")
        for item in report["drift"]:
            print(f"{item['harness']}: {item['capability']} - {item['reason']}")
        if report["repair_required"]:
            print(
                "repair required; use the installer documentation for an explicit uvx repair"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
