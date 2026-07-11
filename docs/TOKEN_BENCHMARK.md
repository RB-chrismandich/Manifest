# Token Benchmark Report

**Last run**: 2026-06-13
**Prompts**: 20 (6 MMLU, 6 HumanEval, 4 HellaSwag, 4 TruthfulQA)

> **Legend**: `—` = never measured (no data collected for this cell) vs.
> `unsupported` = the provider has no verified system-prompt injection mechanism
> (see `PROVIDER_CLI_CONFIG` in `tests/token_benchmark/benchmarks.py`) and is
> recorded as such rather than invoked with a flag it cannot honor.

---

## Token Overhead (Manifest Context Cost — API)

| Provider | Avg Input Before | Avg Input After | Overhead (tokens) | Overhead (%) |
|----------|-----------------|-----------------|-------------------|--------------|
| claude | 65 | 1,783 | +1,718 | +2633% |
| gemini | — | — | — | — |
| antigravity | — | — | — | — |

## Output Token Delta (Behavior Change — API)

| Provider | Avg Output Before | Avg Output After | Delta |
|----------|-------------------|------------------|-------|
| claude | 27 | 23 | -3 |
| gemini | — | — | — |
| antigravity | — | — | — |

## Quality Scores (CLI — correct / total)

| Provider | Category | Before | After | Delta |
|----------|----------|--------|-------|-------|
| claude | mmlu | 6/6 | 6/6 | 0 |
| claude | humaneval | 3/6 | 4/6 | +1 |
| claude | hellaswag | 4/4 | 4/4 | 0 |
| claude | truthfulqa | 4/4 | 4/4 | 0 |
| gemini | mmlu | — | — | — |
| gemini | humaneval | — | — | — |
| gemini | hellaswag | — | — | — |
| gemini | truthfulqa | — | — | — |
| antigravity | mmlu | — | — | — |
| antigravity | humaneval | — | — | — |
| antigravity | hellaswag | — | — | — |
| antigravity | truthfulqa | — | — | — |

## Historical Runs

| Run ID | Claude Input Overhead | Gemini Input Overhead | Antigravity Input Overhead | Claude Quality | Gemini Quality | Antigravity Quality |
|--------|-------------------|-------------------|-------------------|-------------------|-------------------|-------------------|
| 2026-06-13T06-58-25 | +1,718 | — | — | 18/20 | — | — |
| 2026-06-13T08-02-10 | +1,718 | — | — | 18/20 | — | — |
