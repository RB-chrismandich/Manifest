# Token Cost Optimization Benchmark — Design Spec

**Date**: 2026-06-13
**Status**: Approved
**Builds on**: `2026-06-12-token-benchmark-design.md`

---

## Problem

The existing token benchmark measures quality delta (before vs after manifest injection) and token counts, but does not measure **cost**. All agents are one-shot (stateless), so the dominant cost levers are: prompt caching, selective/tiered injection, and system prompt compression. There is currently no way to quantify savings from these strategies.

---

## Goal

Extend the benchmark harness and reporter to measure three cost-reduction strategies and produce a cost analysis table in `TOKEN_BENCHMARK.md` alongside the existing quality table.

---

## Scope

Three new benchmark conditions added to the existing `before` / `after` structure:

| Condition | Strategy | Expected saving |
|-----------|----------|-----------------|
| `cached` | Anthropic prompt caching on system prompt | ~87% on system prompt cost |
| `tiered` | Manifest injected only for HumanEval; baseline elsewhere | ~67% fewer input tokens overall (6/20 prompts inject manifest) |
| `compressed` | 50%-trimmed CLAUDE.md fixture | ~48% fewer system prompt tokens |

---

## Architecture

### 1. Schema — new record fields

Every JSONL record gains:

```python
"cost_usd": float | None           # total cost for this call
"cache_creation_tokens": int | None  # tokens written to cache (Anthropic API)
"cache_read_tokens": int | None      # tokens read from cache (Anthropic API)
```

Records without cost data (CLI path, errors, old runs) use `None` — backwards compatible.

### 2. Pricing constants (`harness.py`)

```python
PRICING = {
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,  # 1.25× input price
        "cache_read":  0.30 / 1_000_000,  # 0.1× input price
    },
    "gemini-3-flash-preview": {
        "input":  0.10 / 1_000_000,
        "output": 0.40 / 1_000_000,
    },
}
```

`compute_cost(record, model) -> float | None` uses these constants. Cache read tokens are billed at `cache_read` rate; remaining input tokens at `input` rate.

### 3. New conditions

**`cached`**
- Identical to `after` but adds `cache_control: {"type": "ephemeral"}` to the Anthropic system prompt block
- Each prompt is called twice: first to seed the cache, second to measure the warm read
- Only the warm read is recorded (the seed call is discarded)
- API usage fields mapped to record fields: `cache_creation_input_tokens` → `cache_creation_tokens`, `cache_read_input_tokens` → `cache_read_tokens`
- Gemini: not supported; condition skipped for Gemini provider

**`tiered`**
- Per-prompt decision: `prompt.category == "humaneval"` → inject manifest (like `after`); all other categories → use baseline (like `before`)
- No new fixtures required
- Rationale: benchmark shows manifest adds 0 quality gain to MMLU/HellaSwag/TruthfulQA; these are already at ceiling

**`compressed`**
- Uses `tests/token_benchmark/fixtures/fixtures-compressed/.claude/CLAUDE.md` — a pre-committed 50%-trimmed version of the manifest CLAUDE.md
- `--sync-fixtures --compression 50` generates this file (first 50% of lines)
- One compression level for now; additional levels can be added as separate fixtures

### 4. `--conditions` flag

```
python3 tests/token_benchmark/harness.py --conditions before,after,cached,tiered,compressed
```

Default: `before,after` (existing behaviour unchanged).

### 5. Reporter — Cost Analysis section

`compute_stats()` gains a `cost_summary` key: per-condition averages for `cost_usd`, `input_tokens`, `quality_score`.

`render_report()` appends a **Cost Analysis** section when cost records are present:

```markdown
## Cost Analysis

| Condition  | Avg input tok | Avg cost/call | Quality | vs after |
|------------|--------------|---------------|---------|----------|
| before     | 65           | $0.000195     | 0.875   | —        |
| after      | 1,783        | $0.000534     | 0.900   | baseline |
| cached     | 1,783        | $0.000071     | 0.900   | +87%     |
| tiered     | 580          | $0.000174     | 0.900   | +67%     |
| compressed | 923          | $0.000277     | 0.892   | +48%     |
```

Section is omitted entirely when no records have `cost_usd` — old JSONL files render the existing quality-only report without modification.

---

## Files

| File | Change |
|------|--------|
| `tests/token_benchmark/harness.py` | `PRICING`, `compute_cost()`, `cache_control` in `measure_api_claude`, tiered condition logic, `--conditions` flag |
| `tests/token_benchmark/reporter.py` | `cost_summary` in `compute_stats()`, Cost Analysis section in `render_report()` |
| `tests/token_benchmark/fixtures/fixtures-compressed/.claude/CLAUDE.md` | New pre-committed compressed fixture (50% of lines) |
| `tests/python/token_benchmark/test_harness.py` | 5 new tests |
| `tests/python/token_benchmark/test_reporter.py` | 3 new tests |

---

## Tests

**`test_harness.py` additions**
- `test_compute_cost_standard` — standard tokens → correct `cost_usd`
- `test_compute_cost_with_cache_read` — cache read tokens billed at 0.1× rate
- `test_cached_condition_passes_cache_control` — API called with `cache_control` block
- `test_tiered_injects_manifest_only_for_humaneval` — correct system prompt per category
- `test_compressed_fixture_loads` — `--sync-fixtures --compression 50` produces 50% line count

**`test_reporter.py` additions**
- `test_cost_table_rendered` — cost section present when records have `cost_usd`
- `test_cost_table_omitted_when_no_cost_data` — backwards compat with old JSONL
- `test_cost_savings_percentage` — `vs after` column computed correctly

All 66 existing tests pass unchanged — new fields default to `None`.

---

## Non-goals

- Multi-turn / conversation cost tracking (all calls are one-shot)
- Gemini caching (API does not expose cache hit tokens the same way)
- Dynamic compression levels at runtime (use pre-committed fixtures for reproducibility)
- Model routing (Haiku vs Sonnet) — separate concern, out of scope for this spec
