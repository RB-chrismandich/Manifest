"""Workflow-suite result splitting, aggregation, and Markdown rendering.

Kept separate from `tests/token_benchmark/reporter.py` (the academic-suite
renderer) so the two responsibilities stay independently sized and testable;
`reporter.update_report()` composes both.
"""

from __future__ import annotations

from collections import defaultdict


def split_suites(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate legacy academic rows from version-2 `workflow` rows before
    any legacy aggregation — workflow conditions (none/slim/full) must never
    reach compute_stats()'s academic before/after buckets."""
    workflow = [r for r in records if r.get("suite") == "workflow"]
    academic = [r for r in records if r.get("suite") != "workflow"]
    return academic, workflow


def _workflow_group_key(record: dict) -> tuple:
    """Group only rows sharing the same fixture/context identity, resolved
    model/effort, tool access, and trial protocol (condition)."""
    return (
        record.get("fixture_id"),
        record.get("condition"),
        record.get("provider"),
        record.get("model"),
        record.get("effort"),
        tuple(record.get("tool_access") or []),
        record.get("fixture_hash"),
        record.get("context_hash"),
    )


def _avg(values: list) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None


def _workflow_cell(key: tuple, rows: list[dict]) -> dict:
    fixture_id, condition, provider, model, _effort, _tools, _fhash, _chash = key
    total = len(rows)
    passed = sum(1 for r in rows if r.get("verification") == "passed")
    return {
        "fixture_id": fixture_id,
        "condition": condition,
        "provider": provider,
        "model": model,
        "trials": total,
        "pass_rate": round(passed / total, 3) if total else None,
        "unavailable": sum(1 for r in rows if r.get("verification") == "unavailable"),
        "recovered": sum(
            1 for r in rows if r.get("repair", {}).get("status") == "recovered"
        ),
        "unresolved_repairs": sum(
            1 for r in rows if r.get("repair", {}).get("status") == "unresolved"
        ),
        "missing_usage": sum(1 for r in rows if r.get("input_tokens") is None),
        "avg_latency_ms": _avg([r.get("latency_ms") for r in rows]),
        "avg_input_tokens": _avg([r.get("input_tokens") for r in rows]),
        "avg_output_tokens": _avg([r.get("output_tokens") for r in rows]),
    }


def compute_workflow_stats(records: list[dict]) -> dict:
    """Aggregate `workflow` suite rows only across matching fixture/context
    hash, resolved model/effort, tool access, and trial protocol — never
    mixed with academic rows or across a fixture/context revision change."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        groups[_workflow_group_key(record)].append(record)
    cells = [_workflow_cell(key, rows) for key, rows in groups.items()]
    cells.sort(
        key=lambda c: (c["fixture_id"] or "", c["condition"] or "", c["provider"] or "")
    )
    return {"cells": cells, "record_count": len(records)}


def render_workflow_section(workflow_stats: dict | None) -> list[str]:
    """Render the workflow suite's pass-rate/repair/telemetry table.

    Never renders a savings claim: a `recovered` cell paid a repair cost and
    an `unresolved`/`unavailable` cell has no comparable measured recovery
    cost to compare against, so this table reports repair/telemetry status
    only, not a before/after saving.
    """
    if not workflow_stats or not workflow_stats.get("cells"):
        return []
    lines = [
        "",
        "## Workflow Suite (code-review / security-triage / implementation / documentation)",
        "",
        "> Repair-adjusted savings are not claimed here: a `recovered` cell",
        "> paid repair cost, and an `unresolved`/`unavailable` cell has no",
        "> comparable measured recovery cost to compare against.",
        "",
        "| Fixture | Condition | Provider | Trials | Pass rate | Unavailable | Recovered | Unresolved | Missing usage | Avg latency (ms) | Avg input tok | Avg output tok |",
        "|---------|-----------|----------|--------|-----------|-------------|-----------|------------|----------------|-------------------|----------------|-----------------|",
    ]
    for cell in workflow_stats["cells"]:
        pass_rate = f"{cell['pass_rate']:.0%}" if cell["pass_rate"] is not None else "—"
        avg_latency = (
            f"{cell['avg_latency_ms']:.0f}"
            if cell["avg_latency_ms"] is not None
            else "—"
        )
        avg_in = (
            f"{cell['avg_input_tokens']:.0f}"
            if cell["avg_input_tokens"] is not None
            else "—"
        )
        avg_out = (
            f"{cell['avg_output_tokens']:.0f}"
            if cell["avg_output_tokens"] is not None
            else "—"
        )
        lines.append(
            f"| {cell['fixture_id']} | {cell['condition']} | {cell['provider']} | "
            f"{cell['trials']} | {pass_rate} | {cell['unavailable']} | {cell['recovered']} | "
            f"{cell['unresolved_repairs']} | {cell['missing_usage']} | {avg_latency} | {avg_in} | {avg_out} |"
        )
    lines.append("")
    return lines
