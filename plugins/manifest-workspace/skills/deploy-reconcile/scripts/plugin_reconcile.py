#!/usr/bin/env python3
"""Compare installation receipts with the packaged domain catalog read-only."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

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


def shared_env_check():
    """Load the bundle-local receipt and native evidence contract."""
    env_script = (
        Path(__file__).resolve().parents[2] / "env-check" / "scripts" / "env_check.py"
    )
    return runpy.run_path(str(env_script))


def reconcile(native_evidence: str | None = None) -> dict:
    env_check = shared_env_check()
    assessment = env_check["assess"](native_evidence)
    receipt = assessment["receipt"]
    drift: list[dict[str, str]] = [
        {"capability": "installation-receipt", "harness": "all", "reason": problem}
        for problem in assessment["problems"]
    ]
    comparison = assessment["comparison"]
    drift.extend(
        {
            "capability": "native-installation",
            "harness": item["harness"],
            "reason": item["reason"],
        }
        for item in comparison["drift"]
    )
    for harness, record in receipt["claims"].items():
        installed = {item.split("@", 1)[0] for item in record["plugin_ids"]}
        missing = sorted(EXPECTED_BUNDLES - installed)
        if missing:
            drift.append(
                {
                    "capability": ",".join(missing),
                    "harness": harness,
                    "reason": "domain plugins absent from receipt inventory",
                }
            )
    status = assessment["status"]
    if status not in {"unverified", "degraded"}:
        status = "drift" if drift else "converged"
    return {
        "drift": drift,
        "harnesses": comparison["harnesses"],
        "native_observed": comparison["native_observed"],
        "receipt": receipt["path"],
        "repair_required": bool(drift),
        "status": status,
        "authentication": "not_tested",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--native-evidence",
        metavar="PATH",
        help="saved manifest reconcile --json output, or - for stdin",
    )
    args = parser.parse_args(argv)
    report = reconcile(args.native_evidence)
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
