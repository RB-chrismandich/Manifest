"""Tests for TOKEN_BENCHMARK.md report generator."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.reporter import (
    compute_stats,
    load_results,
    render_report,
    update_report,
)

# Minimal fixture: 4 records covering one provider/category in before+after
FIXTURE_RECORDS = [
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "condition": "before",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": 100,
        "output_tokens": 5,
        "quality_score": 1,
        "source": "api",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "condition": "after",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": 2635,
        "output_tokens": 7,
        "quality_score": 1,
        "source": "api",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": None,
        "condition": "before",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": None,
        "output_tokens": None,
        "quality_score": 1,
        "source": "cli",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": None,
        "condition": "after",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": None,
        "output_tokens": None,
        "quality_score": 1,
        "source": "cli",
        "error": None,
    },
]


class TestLoadResults:
    def test_loads_jsonl_files(self, tmp_path):
        (tmp_path / "2026-06-12T10-00-00.jsonl").write_text(
            "\n".join(json.dumps(r) for r in FIXTURE_RECORDS)
        )
        records = load_results(tmp_path)
        assert len(records) == 4

    def test_empty_dir_returns_empty_list(self, tmp_path):
        assert load_results(tmp_path) == []

    def test_skips_non_jsonl_files(self, tmp_path):
        (tmp_path / "README.md").write_text("not a result")
        (tmp_path / "run.jsonl").write_text(json.dumps(FIXTURE_RECORDS[0]))
        records = load_results(tmp_path)
        assert len(records) == 1


class TestComputeStats:
    def test_computes_token_overhead(self):
        stats = compute_stats(FIXTURE_RECORDS)
        claude_api = stats["token_overhead"]["claude"]
        assert claude_api["avg_input_before"] == 100
        assert claude_api["avg_input_after"] == 2635
        assert claude_api["overhead_tokens"] == 2535

    def test_computes_output_delta(self):
        stats = compute_stats(FIXTURE_RECORDS)
        claude_api = stats["output_delta"]["claude"]
        assert claude_api["avg_output_before"] == 5
        assert claude_api["avg_output_after"] == 7

    def test_computes_quality_scores(self):
        stats = compute_stats(FIXTURE_RECORDS)
        # Both before and after CLI scores are 1/1 for mmlu
        q = stats["quality"]["claude"]["mmlu"]
        assert q["before_score"] == 1
        assert q["after_score"] == 1
        assert q["before_total"] == 1

    def test_antigravity_records_unsupported_outcome(self):
        """(#546) Antigravity has no verified system-prompt injection
        mechanism, so its CLI rows carry an explicit "unsupported" outcome —
        distinct from "error" and from a normally-scored row — in both the
        before and after conditions, and produce no token overhead (CLI never
        reports tokens for any provider)."""
        records = [
            {
                "run_id": "2026-06-12T10-00-00",
                "provider": "antigravity",
                "model": None,
                "condition": "before",
                "category": "mmlu",
                "prompt_id": "mmlu_001",
                "input_tokens": None,
                "output_tokens": None,
                "quality_score": None,
                "response_text": None,
                "source": "cli",
                "error": None,
                "unsupported": True,
            },
            {
                "run_id": "2026-06-12T10-00-00",
                "provider": "antigravity",
                "model": None,
                "condition": "after",
                "category": "mmlu",
                "prompt_id": "mmlu_001",
                "input_tokens": None,
                "output_tokens": None,
                "quality_score": None,
                "response_text": None,
                "source": "cli",
                "error": None,
                "unsupported": True,
            },
        ]
        stats = compute_stats(records)
        # No API records at all => no token overhead entry for antigravity.
        assert stats["token_overhead"].get("antigravity") is None
        # Unsupported rows must never masquerade as a scored quality row.
        assert stats["quality"].get("antigravity", {}).get("mmlu", {}) == {}
        # Every row is explicitly unsupported, and that is distinct from an
        # error outcome (error stays None) and from a real quality score.
        assert all(r["unsupported"] is True for r in records)
        assert all(r["error"] is None for r in records)
        assert all(r["quality_score"] is None for r in records)
        assert {r["condition"] for r in records} == {"before", "after"}


class TestRenderReport:
    def test_renders_markdown_string(self):
        stats = compute_stats(FIXTURE_RECORDS)
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        assert "# Token Benchmark Report" in md
        assert "Token Overhead" in md
        assert "Quality Scores" in md
        assert "claude" in md.lower()

    def test_includes_overhead_numbers(self):
        stats = compute_stats(FIXTURE_RECORDS)
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        assert "2,535" in md  # overhead tokens (comma-formatted)
        assert "2,635" in md  # avg input after (comma-formatted)

    def test_legend_distinguishes_unsupported_from_never_measured(self):
        """(#546) The report legend explicitly distinguishes a `—` cell
        (never measured) from an `unsupported` provider outcome."""
        stats = compute_stats(FIXTURE_RECORDS)
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        assert "never measured" in md
        assert "unsupported" in md


class TestUpdateReport:
    def test_creates_report_file(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "run.jsonl").write_text(
            "\n".join(json.dumps(r) for r in FIXTURE_RECORDS)
        )
        output = tmp_path / "TOKEN_BENCHMARK.md"
        update_report(results_dir, output)
        assert output.exists()
        assert "Token Benchmark Report" in output.read_text()


class TestConsistentProviderRendering:
    """(#546/G11) Every table is driven by the same provider set — a provider
    with only `unsupported` CLI rows must still get a row/column in every
    table, rendered as `unsupported` rather than silently dropped."""

    UNSUPPORTED_RECORDS = [
        {
            "run_id": "2026-07-11T00-00-00",
            "provider": "antigravity",
            "model": None,
            "condition": cond,
            "category": "mmlu",
            "prompt_id": "mmlu_001",
            "input_tokens": None,
            "output_tokens": None,
            "quality_score": None,
            "response_text": None,
            "source": "cli",
            "error": None,
            "unsupported": True,
        }
        for cond in ("before", "after")
    ] + [
        {
            "run_id": "2026-07-11T00-00-00",
            "provider": "gemini",
            "model": None,
            "condition": cond,
            "category": "mmlu",
            "prompt_id": "mmlu_001",
            "input_tokens": None,
            "output_tokens": None,
            "quality_score": None,
            "response_text": None,
            "source": "cli",
            "error": None,
            "unsupported": True,
        }
        for cond in ("before", "after")
    ]

    def test_output_delta_table_renders_antigravity_as_unsupported(self):
        stats = compute_stats(self.UNSUPPORTED_RECORDS)
        md = render_report(stats, run_id="2026-07-11T00-00-00")
        delta_section = md.split("## Output Token Delta")[1].split("##")[0]
        assert (
            "| antigravity | unsupported | unsupported | unsupported |" in delta_section
        )
        assert "| gemini | unsupported | unsupported | unsupported |" in delta_section

    def test_historical_runs_table_includes_antigravity_column(self):
        stats = compute_stats(self.UNSUPPORTED_RECORDS)
        md = render_report(stats, run_id="2026-07-11T00-00-00")
        historical_section = md.split("## Historical Runs")[1].split("##")[0]
        assert "Antigravity Input Overhead" in historical_section
        assert "Antigravity Quality" in historical_section
        assert "unsupported" in historical_section

    def test_never_measured_stays_dash_not_unsupported(self):
        """A provider absent from every record (never run) still renders `—`,
        not `unsupported` — the two states must stay distinguishable."""
        stats = compute_stats(FIXTURE_RECORDS)  # claude-only fixture
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        delta_section = md.split("## Output Token Delta")[1].split("##")[0]
        assert "| gemini | — | — | — |" in delta_section
        assert "| antigravity | — | — | — |" in delta_section

    def test_compute_stats_defensively_gets_unsupported_key(self):
        """Records from the API path (and older JSONL) never carry the
        `unsupported` key at all; compute_stats must not KeyError on them."""
        api_only_records = [
            {
                "run_id": "2026-07-11T00-00-00",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "condition": "before",
                "category": "mmlu",
                "prompt_id": "mmlu_001",
                "input_tokens": 100,
                "output_tokens": 5,
                "quality_score": 1,
                "source": "api",
                "error": None,
                # no "unsupported" key present
            }
        ]
        stats = compute_stats(api_only_records)  # must not raise KeyError
        assert stats["unsupported_providers"] == []


class TestCostAnalysis:
    def _make_cost_records(self, run_id="2026-06-13T08-00-00"):
        """Minimal records covering before/after/cached/tiered/compressed."""
        base = {
            "run_id": run_id,
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "category": "mmlu",
            "prompt_id": "mmlu_001",
            "quality_score": 1,
            "response_text": "B",
            "latency_ms": 1000,
            "source": "api",
            "error": None,
            "cache_creation_tokens": None,
            "cache_read_tokens": None,
        }
        return [
            {
                **base,
                "condition": "before",
                "input_tokens": 65,
                "output_tokens": 4,
                "cost_usd": 0.000255,
            },
            {
                **base,
                "condition": "after",
                "input_tokens": 1783,
                "output_tokens": 4,
                "cost_usd": 0.000594,
            },
            {
                **base,
                "condition": "cached",
                "input_tokens": 1783,
                "output_tokens": 4,
                "cost_usd": 0.000075,
                "cache_read_tokens": 1718,
            },
            {
                **base,
                "condition": "tiered",
                "input_tokens": 65,
                "output_tokens": 4,
                "cost_usd": 0.000255,
            },
            {
                **base,
                "condition": "compressed",
                "input_tokens": 923,
                "output_tokens": 4,
                "cost_usd": 0.000309,
            },
        ]

    def test_cost_table_rendered(self):
        """Cost Analysis section appears when records have cost_usd."""
        from tests.token_benchmark.reporter import compute_stats, render_report

        records = self._make_cost_records()
        stats = compute_stats(records)
        md = render_report(stats, "2026-06-13T08-00-00")
        assert "## Cost Analysis" in md
        assert "cached" in md
        assert "tiered" in md
        assert "compressed" in md

    def test_cost_table_omitted_when_no_cost_data(self):
        """Cost Analysis section absent when all cost_usd are None (old JSONL)."""
        from tests.token_benchmark.reporter import compute_stats, render_report

        records = self._make_cost_records()
        for r in records:
            r["cost_usd"] = None
        stats = compute_stats(records)
        md = render_report(stats, "2026-06-13T08-00-00")
        assert "## Cost Analysis" not in md

    def test_cost_savings_percentage(self):
        """vs after column shows correct percentage savings."""
        from tests.token_benchmark.reporter import compute_stats, render_report

        records = self._make_cost_records()
        stats = compute_stats(records)
        md = render_report(stats, "2026-06-13T08-00-00")
        # cached should show large savings vs after
        # (0.000594 - 0.000075) / 0.000594 ≈ 0.874 → +87%
        assert "+87%" in md
