"""Regression tests for the three token/skill measurement report CLIs.

token_cost_report.py, skill_usage_report.py, and opus_attribution_report.py
scan Claude Code JSONL transcripts and had ZERO test coverage before this
file, despite five real defects found by manual probing (requestId dedup
using sum instead of max, non-deterministic --json snapshots under a
growing corpus, string-compared timestamps silently accepting garbage,
false-green empty results, and unhandled --json write failures).

Every fixture here is synthetic and written into pytest's ``tmp_path`` --
never the live ``~/.claude/projects`` corpus -- so these tests are hermetic
and fast. Scripts are invoked as subprocesses (the real CLI surface), not
imported and called directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "configs/claude/scripts"
TOKEN_COST = SCRIPTS / "token_cost_report.py"
SKILL_USAGE = SCRIPTS / "skill_usage_report.py"
OPUS_ATTR = SCRIPTS / "opus_attribution_report.py"

ALL_SCRIPTS = [TOKEN_COST, SKILL_USAGE, OPUS_ATTR]


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def usage_record(
    request_id: str,
    timestamp: str,
    *,
    output_tokens: int = 5,
    input_tokens: int = 10,
    cache_read: int = 1000,
    cache_creation: int = 100,
    model: str = "claude-opus-4-8",
    content: list[dict] | None = None,
    is_sidechain: bool = False,
) -> dict:
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "requestId": request_id,
        "isSidechain": is_sidechain,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
            "content": content
            if content is not None
            else [{"type": "text", "text": "hi"}],
        },
    }


# --- 1. Dedup reducer: one requestId, three content-block siblings --------
# The transcript format writes one JSONL line per content block of a single
# API response, repeating the same `usage` object on every sibling line.
# output_tokens is a cumulative/streaming total (last-written == max); the
# other usage fields are per-request constants. A naive per-line sum
# multiply-counts everything; this must be exactly deduped instead.


def test_dedup_reducer_one_request_max_output_single_count(tmp_path):
    records = [
        usage_record(
            "req_A",
            "2026-07-01T12:00:00Z",
            output_tokens=5,
            content=[{"type": "thinking"}],
        ),
        usage_record(
            "req_A",
            "2026-07-01T12:00:01Z",
            output_tokens=40,
            content=[{"type": "text", "text": "partial"}],
        ),
        usage_record(
            "req_A",
            "2026-07-01T12:00:02Z",
            output_tokens=123,
            content=[{"type": "tool_use", "name": "Bash", "input": {}}],
        ),
    ]
    write_jsonl(tmp_path / "proj" / "session.jsonl", records)
    json_out = tmp_path / "out.json"

    r = run(TOKEN_COST, "--root", str(tmp_path), "--json", str(json_out))
    assert r.returncode == 0, r.stderr

    data = json.loads(json_out.read_text())
    assert data["api_requests"] == 1
    assert data["assistant_lines"] == 3  # raw lines still 3, deduped to 1 request
    assert data["agg"]["output_tokens"] == 123  # MAX of 5/40/123, not the 168 sum
    assert data["agg"]["input_tokens"] == 10  # counted once, not x3
    assert data["agg"]["cache_read_input_tokens"] == 1000
    assert data["agg"]["cache_creation_input_tokens"] == 100
    assert data["agg"]["api_calls"] == 1


# --- 2. Snapshot determinism under corpus growth --------------------------
# The single highest-value test: a fixed --until must yield byte-identical
# --json output even after new transcript data (timestamped after the
# cutoff) is appended to the same root. Running the same command twice in
# quick succession would never catch drift; only growing the corpus between
# runs does.


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_snapshot_deterministic_under_corpus_growth(tmp_path, script):
    proj = tmp_path / "proj"
    write_jsonl(
        proj / "s1.jsonl",
        [
            usage_record(
                "req1",
                "2026-01-01T00:00:00Z",
                output_tokens=50,
                model="claude-opus-4-8",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "code-audit"},
                    }
                ],
            ),
            usage_record(
                "req2",
                "2026-01-01T00:05:00Z",
                output_tokens=20,
                model="claude-sonnet-4-5",
                content=[{"type": "tool_use", "name": "Read", "input": {}}],
            ),
        ],
    )
    until = "2026-01-01T01:00:00Z"

    out1 = tmp_path / "out1.json"
    r1 = run(script, "--root", str(tmp_path), "--until", until, "--json", str(out1))
    assert r1.returncode == 0, r1.stderr
    snapshot1 = out1.read_text()

    # Corpus grows: a new transcript lands in the same root, timestamped
    # AFTER the fixed cutoff, before the second run.
    write_jsonl(
        proj / "s2-future.jsonl",
        [
            usage_record(
                "req3",
                "2026-01-02T00:00:00Z",
                output_tokens=999,
                model="claude-opus-4-8",
                content=[{"type": "text", "text": "future"}],
            )
        ],
    )

    out2 = tmp_path / "out2.json"
    r2 = run(script, "--root", str(tmp_path), "--until", until, "--json", str(out2))
    assert r2.returncode == 0, r2.stderr
    snapshot2 = out2.read_text()

    assert snapshot1 == snapshot2, (
        f"{script.name}: --json output drifted after the corpus grew past --until"
    )


# --- 3. Invalid timestamps are rejected, not silently accepted ------------
# Guards the specific bug: a plain string comparison silently accepted
# garbage ("2026-..." > "banana" is False in Python), leaving the window
# effectively unbounded while still exiting 0.


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
@pytest.mark.parametrize("flag", ["--until", "--since"])
def test_invalid_timestamp_rejected(tmp_path, script, flag):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [usage_record("req1", "2026-01-01T00:00:00Z")],
    )
    json_out = tmp_path / "out.json"
    r = run(script, "--root", str(tmp_path), flag, "banana", "--json", str(json_out))
    assert r.returncode != 0, r.stdout
    assert not json_out.exists(), "a rejected timestamp must not emit a report"


# --- 4. Nonexistent --root exits non-zero, not a clean empty result ------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_nonexistent_root_exits_nonzero(tmp_path, script):
    missing_root = tmp_path / "does-not-exist"
    r = run(script, "--root", str(missing_root))
    assert r.returncode != 0, (
        f"{script.name}: a missing --root must not report a clean zero-cost run"
    )


# --- 5. Empty result sets never raise a traceback -------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_inverted_window_exits_nonzero_no_traceback(tmp_path, script):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            usage_record(
                "req1",
                "2026-01-01T12:00:00Z",
                model="claude-opus-4-8",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "code-audit"},
                    }
                ],
            )
        ],
    )
    r = run(
        script,
        "--root",
        str(tmp_path),
        "--since",
        "2026-06-01T00:00:00Z",
        "--until",
        "2026-01-01T00:00:00Z",
    )
    assert r.returncode != 0, r.stdout
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("script", [TOKEN_COST, OPUS_ATTR], ids=lambda s: s.name)
def test_no_usage_records_exits_nonzero_no_traceback(tmp_path, script):
    # A transcript with assistant lines but no usage object at all -- must
    # not raise (e.g. a raw ZeroDivisionError) while computing shares/ratios
    # over an empty aggregate.
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            {
                "type": "assistant",
                "timestamp": "2026-01-01T00:00:00Z",
                "requestId": "req1",
                "isSidechain": False,
                "message": {
                    "model": "claude-opus-4-8",
                    "content": [{"type": "text", "text": "hi"}],
                },
            }
        ],
    )
    r = run(script, "--root", str(tmp_path))
    assert r.returncode != 0, r.stdout
    assert "Traceback" not in r.stderr


# --- 6. Unwritable --json path exits non-zero, no traceback ---------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda s: s.name)
def test_unwritable_json_path_exits_nonzero_no_traceback(tmp_path, script):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            usage_record(
                "req1",
                "2026-01-01T00:00:00Z",
                model="claude-opus-4-8",
                content=[
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "code-audit"},
                    }
                ],
            )
        ],
    )
    bad_json = tmp_path / "no-such-dir" / "out.json"
    r = run(script, "--root", str(tmp_path), "--json", str(bad_json))
    assert r.returncode != 0, r.stdout
    assert "Traceback" not in r.stderr
    assert not bad_json.exists()


# --- 7. Class x model matrix: the routing lever is verifiable at all ------
# The baseline's headline row -- "Fable 5 sub-agents: 4,531 requests,
# $919.32" -- came from ad-hoc analysis: opus_attribution_report.py hard-
# filtered to Opus and token_cost_report.py had no class awareness, so no
# committed script could re-derive it. The gates could then only prove that
# command_config.yml *says* Sonnet, never that a dispatch *ran* Sonnet.
# These tests pin the query that closes that gap.

# 800,000 cache-creation tokens weight to exactly 1,000,000 input units
# (x1.25), so a model's whole input cost is one clean $/MTok multiple.
CLEAN_TOKENS = {"input_tokens": 0, "cache_read": 0, "cache_creation": 800_000}


def subagent_record(request_id, timestamp, model, **kw):
    """A sidechain request -- what classify() calls the `subagent` class."""
    return usage_record(
        request_id,
        timestamp,
        model=model,
        is_sidechain=True,
        output_tokens=100_000,
        content=[{"type": "text", "text": "done"}],
        **{**CLEAN_TOKENS, **kw},
    )


def test_matrix_costs_each_class_model_cell(tmp_path):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            subagent_record("req_f", "2026-07-01T00:00:00Z", "claude-fable-5"),
            subagent_record("req_s", "2026-07-01T00:01:00Z", "claude-sonnet-5"),
        ],
    )
    out = tmp_path / "out.json"
    r = run(OPUS_ATTR, "--root", str(tmp_path), "--models", "all", "--json", str(out))
    assert r.returncode == 0, r.stderr

    matrix = json.loads(out.read_text())["class_model_matrix"]
    # 1M weighted input units + 100K output, priced per model:
    #   fable  $10/MTok in + $50/MTok out -> 10.00 + 5.00 = 15.00
    #   sonnet  $3/MTok in + $15/MTok out ->  3.00 + 1.50 =  4.50
    assert matrix["subagent"]["claude-fable-5"]["cost_usd"] == 15.00
    assert matrix["subagent"]["claude-sonnet-5"]["cost_usd"] == 4.50
    assert matrix["subagent"]["claude-fable-5"]["requests"] == 1


def test_unknown_model_is_unpriced_never_zero(tmp_path):
    # A model missing from the price table must read as a HOLE in the total,
    # not as a $0 line -- a silent zero is the same false-green shape as a
    # gate that checks the doc instead of the behaviour.
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [subagent_record("req_x", "2026-07-01T00:00:00Z", "claude-notreal-9")],
    )
    out = tmp_path / "out.json"
    r = run(OPUS_ATTR, "--root", str(tmp_path), "--models", "all", "--json", str(out))
    assert r.returncode == 0, r.stderr

    data = json.loads(out.read_text())
    cell = data["class_model_matrix"]["subagent"]["claude-notreal-9"]
    assert cell["cost_usd"] is None, "an unpriced model must not report a cost"
    assert data["unpriced_models"] == {"claude-notreal-9": 1}
    # The class rollup must refuse to state a total it cannot compute.
    assert data["classes"]["subagent"]["cost_usd"] is None
    assert "UNPRICED" in r.stdout


def test_models_filter_defaults_to_opus_and_all_widens_it(tmp_path):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            subagent_record("req_o", "2026-07-01T00:00:00Z", "claude-opus-4-8"),
            subagent_record("req_f", "2026-07-01T00:01:00Z", "claude-fable-5"),
        ],
    )
    default_out = tmp_path / "default.json"
    r = run(OPUS_ATTR, "--root", str(tmp_path), "--json", str(default_out))
    assert r.returncode == 0, r.stderr
    default_models = json.loads(default_out.read_text())["class_model_matrix"][
        "subagent"
    ]
    assert set(default_models) == {"claude-opus-4-8"}

    all_out = tmp_path / "all.json"
    r = run(
        OPUS_ATTR, "--root", str(tmp_path), "--models", "all", "--json", str(all_out)
    )
    assert r.returncode == 0, r.stderr
    all_models = json.loads(all_out.read_text())["class_model_matrix"]["subagent"]
    assert set(all_models) == {"claude-opus-4-8", "claude-fable-5"}


def test_since_change_point_shows_a_cell_going_to_zero(tmp_path):
    # The lever-1 verification query itself: sub-agents ran on Fable before
    # the change point and on Sonnet after it, so `--since <change-point>`
    # must show subagent x fable absent -- evidence a dispatch actually moved.
    change_point = "2026-07-25T23:58:27Z"
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            subagent_record("req_before", "2026-07-25T12:00:00Z", "claude-fable-5"),
            subagent_record("req_after", "2026-07-26T12:00:00Z", "claude-sonnet-5"),
        ],
    )
    after = tmp_path / "after.json"
    r = run(
        OPUS_ATTR,
        "--root",
        str(tmp_path),
        "--models",
        "all",
        "--since",
        change_point,
        "--json",
        str(after),
    )
    assert r.returncode == 0, r.stderr

    post = json.loads(after.read_text())["class_model_matrix"]["subagent"]
    assert "claude-fable-5" not in post, "premium sub-agent traffic did not go to zero"
    assert post["claude-sonnet-5"]["requests"] == 1


def test_token_cost_report_costs_every_model(tmp_path):
    write_jsonl(
        tmp_path / "proj" / "s.jsonl",
        [
            subagent_record("req_f", "2026-07-01T00:00:00Z", "claude-fable-5"),
            subagent_record("req_u", "2026-07-01T00:01:00Z", "claude-notreal-9"),
        ],
    )
    out = tmp_path / "out.json"
    r = run(TOKEN_COST, "--root", str(tmp_path), "--json", str(out))
    assert r.returncode == 0, r.stderr

    data = json.loads(out.read_text())
    by_model = {row["model"]: row for row in data["cost_by_model"]}
    assert by_model["claude-fable-5"]["cost_usd"] == 15.00
    assert by_model["claude-notreal-9"]["cost_usd"] is None
    assert data["cost_total_usd"] == 15.00  # the unpriced model is a hole, not a $0
    assert data["unpriced_models"] == {"claude-notreal-9": 1}


# --- 8. Price table resolution --------------------------------------------


def test_price_table_resolution():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import model_pricing
    finally:
        sys.path.pop(0)

    # Dated snapshot ids resolve to their undated rate...
    assert model_pricing.rates("claude-haiku-4-5-20251001") == (1.00, 5.00)
    # ...but a model absent from the table must NOT borrow a neighbour's rate.
    assert model_pricing.rates("claude-sonnet-4-5") is None
    assert model_pricing.rates("<synthetic>") is None
    assert model_pricing.rates(None) is None
    assert (
        model_pricing.cost_usd(
            "<synthetic>",
            input_tokens=10**9,
            output_tokens=10**9,
            cache_read=0,
            cache_creation=0,
        )
        is None
    )


# --- --help must exit 0 for every entry point -----------------------------


@pytest.mark.parametrize(
    "script", [*ALL_SCRIPTS, SCRIPTS / "model_pricing.py"], ids=lambda s: s.name
)
def test_help_exits_zero(script):
    r = run(script, "--help")
    assert r.returncode == 0, r.stderr
