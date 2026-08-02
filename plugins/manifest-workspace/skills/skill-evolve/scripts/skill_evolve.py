#!/usr/bin/env python3
"""Inspect SkillClaw proposals stored in bundle-owned XDG data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def proposal_root() -> Path:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "manifest/skill-evolve"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = proposal_root()
    proposals = sorted(str(path.relative_to(root)) for path in root.glob("*/SKILL.md"))
    report = {
        "apply_requested": args.apply,
        "proposals": proposals,
        "root": str(root),
        "status": "degraded" if args.apply else "preview",
    }
    if args.apply:
        report["reason"] = (
            "opening a review PR requires an explicit repository workflow; "
            "bundle runtime never mutates a repository implicitly"
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"skill-evolve: {len(proposals)} proposal(s) in {root}")
        if args.apply:
            print(f"DEGRADED: {report['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
