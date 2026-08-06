#!/usr/bin/env python3
"""Render the authoritative legacy ownership inventory for human review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manifest_agent.migration import load_legacy_inventory  # noqa: E402


def render() -> str:
    """Return a deterministic Markdown table with one row per owned output."""
    inventory = load_legacy_inventory()
    lines = [
        "# Plugin Capability Inventory",
        "",
        "Generated from `src/manifest_agent/data/legacy_inventory.yml`; do not edit by hand.",
        "Unlisted paths and credential stores are user-owned and are never changed by migration.",
        "",
        "| ID | Legacy source | Classification | Native destination | Ownership proof | Action | Recovery | Parity test |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in sorted(inventory.entries, key=lambda candidate: candidate.id):
        lines.append(
            f"| {entry.id} | `{entry.path}` | {entry.classification} | "
            f"{entry.destination} | {entry.ownership_proof.type}: "
            f"`{entry.ownership_proof.value}` | {entry.action} | "
            f"{entry.recovery} | `{entry.parity_test}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail if the checked-in rendering is stale"
    )
    options = parser.parse_args()
    output = ROOT / "docs" / "PLUGIN_CAPABILITY_INVENTORY.md"
    expected = render()
    if options.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print(
                f"{output.relative_to(ROOT)} is stale; run tools/render_capability_inventory.py",
                file=sys.stderr,
            )
            return 1
        return 0
    output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
