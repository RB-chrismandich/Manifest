#!/usr/bin/env python3
"""Inspect installation receipts and installed harness inventories read-only."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HARNESSES = {
    "antigravity": "agy",
    "claude": "claude",
    "codex": "codex",
    "cursor": "cursor-agent",
    "devin": "devin",
    "gemini": "gemini",
}


def receipt_path() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state_home / "manifest/installation.json"


def load_receipt(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "installation receipt is absent"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"installation receipt is unreadable: {error}"
    if not isinstance(document, dict):
        return None, "installation receipt is not a JSON object"
    return document, None


def inspect() -> dict:
    path = receipt_path()
    receipt, receipt_error = load_receipt(path)
    inventories = {
        harness: {"binary": binary, "available": shutil.which(binary) is not None}
        for harness, binary in HARNESSES.items()
    }
    warnings = [receipt_error] if receipt_error else []
    return {
        "inventories": inventories,
        "receipt": {"path": str(path), "present": receipt is not None},
        "status": "degraded" if warnings else "ok",
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = inspect()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"workspace environment: {report['status']}")
        for harness, inventory in report["inventories"].items():
            state = "available" if inventory["available"] else "missing"
            print(f"{harness}: {state} ({inventory['binary']})")
        for warning in report["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
