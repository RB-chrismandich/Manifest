#!/usr/bin/env python3
"""Render the checked release-evidence matrix for the nine domain bundles.

This rendering is deliberately contract evidence, not a substitute for the
protected live workflow.  A live report may be supplied with ``--inspection``;
unknown, skipped, or unverified records make ``--check`` fail instead of
turning a release gate green by omission.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from manifest_agent.contracts import DOMAIN_BUNDLES, CapabilityTier, load_domain_contracts  # noqa: E402

HARNESSES = ("claude", "codex", "gemini", "cursor", "antigravity", "devin")
_COMPONENT_KINDS = (("skill", "skills"), ("agent", "agents"), ("hook", "hooks"), ("runtime", "runtime"), ("guidance", "guidance"))
_ALLOWED_PREFIXES = ("READY", "DEGRADED(", "BLOCKED(", "N/A(")


class MatrixError(ValueError):
    """Evidence is incomplete or malformed."""


def _status(status: Any, *, optional: bool = False) -> str:
    if optional:
        return "N/A(contract optional; not selected)"
    if status.mode in {"native", "generated", "imported"}:
        return "READY"
    if status.mode == "degraded":
        return f"DEGRADED({status.reason or 'contract-declared degradation'})"
    if status.mode == "unsupported":
        return f"N/A({status.reason or 'contract-declared unsupported surface'})"
    return f"BLOCKED(unknown contract compatibility mode {status.mode!r})"


def _inspection_cells(document: dict[str, Any], key: str) -> dict[str, str]:
    record = document.get(key)
    if not isinstance(record, dict):
        return {}
    cells: dict[str, str] = {}
    for harness, raw in record.items():
        if harness not in HARNESSES:
            raise MatrixError(f"inspection {key!r} names unknown harness {harness!r}")
        if not isinstance(raw, str) or not raw.startswith(_ALLOWED_PREFIXES):
            raise MatrixError(f"inspection {key!r}/{harness!r} is not a verified state")
        cells[harness] = raw
    return cells


def _rows(inspection: dict[str, Any] | None = None) -> list[tuple[str, str, list[str]]]:
    contracts = load_domain_contracts(ROOT / "plugins")
    if tuple(contract.name for contract in contracts) != DOMAIN_BUNDLES:
        raise MatrixError("domain contracts are incomplete or unexpectedly ordered")
    rows: list[tuple[str, str, list[str]]] = []
    evidence = inspection or {}
    for contract in contracts:
        def add(identity: str, source: str, statuses: dict[str, Any], optional: bool = False) -> None:
            live = _inspection_cells(evidence, identity)
            cells = [live.get(harness, _status(statuses[harness], optional=optional)) for harness in HARNESSES]
            if any(not cell or not cell.startswith(_ALLOWED_PREFIXES) for cell in cells):
                raise MatrixError(f"{identity}: blank or unverified harness evidence")
            rows.append((identity, source, cells))

        skill_names: set[str] = set()
        root = ROOT / "plugins" / contract.name / contract.components.skills_root
        for include in contract.components.skills_include:
            skill_names.update(path.parent.name for path in root.glob(include) if path.is_file())
        for name in sorted(skill_names):
            add(f"{contract.name}:skill:{name}", "contract skill", dict(contract.compatibility))
        for kind, attribute in _COMPONENT_KINDS[1:]:
            for component in sorted(getattr(contract.components, attribute), key=lambda item: item.id):
                add(
                    f"{contract.name}:{kind}:{component.id}",
                    f"contract {kind}",
                    dict(component.compatibility or contract.compatibility),
                )
        for capability_kind, values in (("mcp", contract.capabilities.mcp), ("executable", contract.capabilities.executables)):
            for tier in CapabilityTier:
                for identifier in values[tier]:
                    add(
                        f"{contract.name}:{capability_kind}:{identifier}",
                        f"contract {tier.value} {capability_kind}",
                        dict(contract.compatibility),
                        optional=tier is CapabilityTier.OPTIONAL,
                    )
    return rows


def render(inspection: dict[str, Any] | None = None) -> str:
    """Return deterministic Markdown, one applicability state per cell."""
    lines = [
        "# Plugin Capability Matrix",
        "",
        "Generated from portable contracts and optional adapter inspection evidence; do not edit by hand.",
        "`READY` is a contract/native-view representation result. The protected six-harness release workflow supplies the live executable verdict.",
        "",
        "| Capability | Evidence | Claude | Codex | Gemini | Cursor | Antigravity | Devin |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for identity, source, cells in _rows(inspection):
        lines.append("| " + " | ".join((f"`{identity}`", source, *cells)) + " |")
    return "\n".join(lines) + "\n"


def _load_inspection(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MatrixError(f"unable to load inspection evidence: {error}") from error
    if not isinstance(parsed, dict):
        raise MatrixError("inspection evidence must be a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--inspection", type=Path)
    args = parser.parse_args(argv)
    try:
        output = render(_load_inspection(args.inspection))
    except MatrixError as error:
        print(f"render_plugin_capability_matrix.py: {error}", file=sys.stderr)
        return 2
    target = ROOT / "docs/PLUGIN_CAPABILITY_MATRIX.md"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != output:
            print("docs/PLUGIN_CAPABILITY_MATRIX.md is stale; run tools/render_plugin_capability_matrix.py", file=sys.stderr)
            return 1
        return 0
    target.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
