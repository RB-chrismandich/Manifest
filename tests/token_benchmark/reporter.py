"""Generate TOKEN_BENCHMARK.md from accumulated JSONL result files."""

import json
from collections import defaultdict
from pathlib import Path

# Canonical provider set, shared by every table so no table can silently drop
# a provider by hard-coding a shorter tuple (#546/G11). Table order == display
# order.
PROVIDERS = ("claude", "gemini", "antigravity")


def load_results(results_dir: Path) -> list[dict]:
    """Read all .jsonl files in results_dir and return a flat list of records."""
    records = []
    for f in sorted(results_dir.glob("*.jsonl")):
        # Optimization: use lazy file iteration instead of f.read_text().splitlines()
        # to prevent loading the entire file into memory at once
        with f.open("r", encoding="utf-8") as fd:
            for line in fd:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def compute_stats(records: list[dict]) -> dict:
    """Aggregate records into summary stats per provider."""
    api_recs = [r for r in records if r.get("source") == "api"]
    cli_recs = [r for r in records if r.get("source") == "cli"]

    # Providers with a verified-absent system-prompt mechanism (#546) record
    # an explicit "unsupported" outcome on their CLI rows. Rows from the API
    # path and older JSONL never carry the key, so always use .get() here —
    # a bare r["unsupported"] would KeyError and break reporting.
    unsupported_providers = {
        r["provider"] for r in records if r.get("unsupported") is True
    }

    # Token overhead (API records with non-null tokens)
    token_overhead = {}
    providers = {r["provider"] for r in api_recs}
    for provider in providers:
        before = [
            r
            for r in api_recs
            if r["provider"] == provider
            and r["condition"] == "before"
            and r.get("input_tokens") is not None
        ]
        after = [
            r
            for r in api_recs
            if r["provider"] == provider
            and r["condition"] == "after"
            and r.get("input_tokens") is not None
        ]
        if not before or not after:
            continue
        avg_in_b = sum(r["input_tokens"] for r in before) / len(before)
        avg_in_a = sum(r["input_tokens"] for r in after) / len(after)
        avg_out_b = sum(r["output_tokens"] for r in before) / len(before)
        avg_out_a = sum(r["output_tokens"] for r in after) / len(after)
        overhead = avg_in_a - avg_in_b
        token_overhead[provider] = {
            "avg_input_before": round(avg_in_b),
            "avg_input_after": round(avg_in_a),
            "overhead_tokens": round(overhead),
            "overhead_pct": round(overhead / avg_in_b * 100) if avg_in_b else None,
            "avg_output_before": round(avg_out_b),
            "avg_output_after": round(avg_out_a),
            "output_delta": round(avg_out_a - avg_out_b),
        }

    # Quality scores (CLI records)
    quality = defaultdict(
        lambda: defaultdict(
            lambda: {
                "before_score": 0,
                "before_total": 0,
                "after_score": 0,
                "after_total": 0,
            }
        )
    )
    for r in cli_recs:
        if r.get("quality_score") is None:
            continue
        provider = r["provider"]
        category = r["category"]
        cond = r["condition"]
        quality[provider][category][f"{cond}_score"] += r["quality_score"]
        quality[provider][category][f"{cond}_total"] += 1

    # Cost summary per condition (API records with non-null cost_usd)
    cost_records = [r for r in api_recs if r.get("cost_usd") is not None]
    cost_summary: dict = {}
    if cost_records:
        all_conditions = sorted({r["condition"] for r in cost_records})
        after_cost: float | None = None
        for cond in all_conditions:
            cond_recs = [r for r in cost_records if r["condition"] == cond]
            avg_cost = sum(r["cost_usd"] for r in cond_recs) / len(cond_recs)
            valid_input = [r for r in cond_recs if r.get("input_tokens") is not None]
            avg_input = (
                sum(r["input_tokens"] for r in valid_input) / len(valid_input)
                if valid_input
                else 0
            )
            valid_quality = [r for r in cond_recs if r.get("quality_score") is not None]
            avg_quality = (
                sum(r["quality_score"] for r in valid_quality) / len(valid_quality)
                if valid_quality
                else 0.0
            )
            cost_summary[cond] = {
                "avg_cost_usd": avg_cost,
                "avg_input_tokens": round(avg_input),
                "avg_quality": round(avg_quality, 3),
                "savings_vs_after_pct": None,
            }
            if cond == "after":
                after_cost = avg_cost

        if after_cost is not None and after_cost > 0:
            for cond, data in cost_summary.items():
                if cond != "after":
                    savings = (after_cost - data["avg_cost_usd"]) / after_cost
                    data["savings_vs_after_pct"] = round(savings * 100)

    return {
        "token_overhead": token_overhead,
        "output_delta": {
            p: {
                "avg_output_before": v["avg_output_before"],
                "avg_output_after": v["avg_output_after"],
                "output_delta": v["output_delta"],
            }
            for p, v in token_overhead.items()
        },
        "quality": {p: dict(cats) for p, cats in quality.items()},
        "run_ids": sorted({r["run_id"] for r in records}),
        "cost_summary": cost_summary,
        "unsupported_providers": sorted(unsupported_providers),
    }


def _empty_cell(provider: str, unsupported: set[str]) -> str:
    """Render the blank-data cell for a provider: `unsupported` when the
    provider has a verified-absent mechanism for this metric (recorded via
    the row-level `unsupported` flag), else `—` (never measured)."""
    return "unsupported" if provider in unsupported else "—"


def render_report(stats: dict, run_id: str) -> str:
    """Render TOKEN_BENCHMARK.md markdown from computed stats."""
    unsupported = set(stats.get("unsupported_providers", []))
    lines = [
        "# Token Benchmark Report",
        "",
        f"**Last run**: {run_id[:10]}",
        "**Prompts**: 20 (6 MMLU, 6 HumanEval, 4 HellaSwag, 4 TruthfulQA)",
        "",
        "> **Legend**: `—` = never measured (no data collected for this cell) vs.",
        "> `unsupported` = the provider has no verified system-prompt injection mechanism",
        "> (see `PROVIDER_CLI_CONFIG` in `tests/token_benchmark/benchmarks.py`) and is",
        "> recorded as such rather than invoked with a flag it cannot honor.",
        "",
        "---",
        "",
        "## Token Overhead (Manifest Context Cost — API)",
        "",
        "| Provider | Avg Input Before | Avg Input After | Overhead (tokens) | Overhead (%) |",
        "|----------|-----------------|-----------------|-------------------|--------------|",
    ]
    for provider in PROVIDERS:
        d = stats["token_overhead"].get(provider)
        if d:
            lines.append(
                f"| {provider} | {d['avg_input_before']:,} | {d['avg_input_after']:,} "
                f"| +{d['overhead_tokens']:,} | +{d['overhead_pct']}% |"
            )
        else:
            cell = _empty_cell(provider, unsupported)
            lines.append(f"| {provider} | {cell} | {cell} | {cell} | {cell} |")

    lines += [
        "",
        "## Output Token Delta (Behavior Change — API)",
        "",
        "| Provider | Avg Output Before | Avg Output After | Delta |",
        "|----------|-------------------|------------------|-------|",
    ]
    for provider in PROVIDERS:
        d = stats["output_delta"].get(provider)
        if d:
            delta_str = (
                f"+{d['output_delta']}"
                if d["output_delta"] >= 0
                else str(d["output_delta"])
            )
            lines.append(
                f"| {provider} | {d['avg_output_before']} | {d['avg_output_after']} | {delta_str} |"
            )
        else:
            cell = _empty_cell(provider, unsupported)
            lines.append(f"| {provider} | {cell} | {cell} | {cell} |")

    lines += [
        "",
        "## Quality Scores (CLI — correct / total)",
        "",
        "| Provider | Category | Before | After | Delta |",
        "|----------|----------|--------|-------|-------|",
    ]
    for provider in PROVIDERS:
        cats = stats["quality"].get(provider, {})
        for category in ("mmlu", "humaneval", "hellaswag", "truthfulqa"):
            q = cats.get(category, {})
            if q and q.get("before_total", 0) > 0:
                b = f"{q['before_score']}/{q['before_total']}"
                a = f"{q['after_score']}/{q['after_total']}"
                delta = q["after_score"] - q["before_score"]
                d = f"+{delta}" if delta > 0 else str(delta)
                lines.append(f"| {provider} | {category} | {b} | {a} | {d} |")
            else:
                cell = _empty_cell(provider, unsupported)
                lines.append(f"| {provider} | {category} | {cell} | {cell} | {cell} |")

    # Historical Runs columns are driven by PROVIDERS (not a hard-coded
    # claude/gemini pair) so every provider — including agy, which is always
    # `unsupported` here today — gets a column rather than being silently
    # dropped from this table (#546/G11).
    overhead_headers = " | ".join(f"{p.capitalize()} Input Overhead" for p in PROVIDERS)
    quality_headers = " | ".join(f"{p.capitalize()} Quality" for p in PROVIDERS)
    lines += [
        "",
        "## Historical Runs",
        "",
        f"| Run ID | {overhead_headers} | {quality_headers} |",
        "|--------|" + "-------------------|" * (2 * len(PROVIDERS)),
    ]
    for run_id_h in stats.get("run_ids", [])[-10:]:  # last 10 runs
        overhead_cells = []
        quality_cells = []
        for provider in PROVIDERS:
            d = stats["token_overhead"].get(provider)
            overhead_cells.append(
                f"+{d['overhead_tokens']:,}" if d else _empty_cell(provider, unsupported)
            )
            q_cats = stats["quality"].get(provider, {})
            q_total = sum(v.get("after_total", 0) for v in q_cats.values())
            q_score = sum(v.get("after_score", 0) for v in q_cats.values())
            quality_cells.append(
                f"{q_score}/{q_total}" if q_total else _empty_cell(provider, unsupported)
            )
        row = " | ".join([*overhead_cells, *quality_cells])
        lines.append(f"| {run_id_h[:19]} | {row} |")

    cost_summary = stats.get("cost_summary", {})
    if cost_summary:
        lines += [
            "",
            "## Cost Analysis",
            "",
            "> Cost is computed only from the API path (`PRICING` in "
            "`tests/token_benchmark/harness.py`), so this table reflects "
            "claude/gemini only — antigravity has no API/tokenizer path and "
            "is `unsupported` here by design (see legend above).",
            "",
            "| Condition  | Avg input tok | Avg cost/call | Quality | vs after |",
            "|------------|--------------|---------------|---------|----------|",
        ]
        condition_order = ["before", "after", "cached", "tiered", "compressed"]
        for cond in condition_order:
            data = cost_summary.get(cond)
            if not data:
                continue
            savings = data.get("savings_vs_after_pct")
            vs_after = (
                "baseline"
                if cond == "after"
                else ("—" if savings is None else f"{savings:+d}%")
            )
            lines.append(
                f"| {cond:<10} | {data['avg_input_tokens']:>13,} "
                f"| ${data['avg_cost_usd']:.6f}    "
                f"| {data['avg_quality']:.3f}   "
                f"| {vs_after:<8} |"
            )

    lines.append("")
    return "\n".join(lines)


def update_report(results_dir: Path, output_path: Path) -> None:
    """Load all results, compute stats, render, and write TOKEN_BENCHMARK.md."""
    records = load_results(results_dir)
    if not records:
        output_path.write_text(
            "# Token Benchmark Report\n\nNo results yet. Run `/token-benchmark` to populate.\n"
        )
        return
    stats = compute_stats(records)
    latest_run_id = stats["run_ids"][-1] if stats["run_ids"] else "unknown"
    report = render_report(stats, run_id=latest_run_id)
    output_path.write_text(report)
