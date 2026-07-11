# Token Benchmark Report

**Last run**: 2026-07-10
**Prompts**: 20 (6 MMLU, 6 HumanEval, 4 HellaSwag, 4 TruthfulQA)

> **Legend**: `—` = no valid measurements (never run, or all attempts
> errored) vs. `unsupported` = the provider has no verified
> system-prompt injection mechanism (see `PROVIDER_CLI_CONFIG` in
> `tests/token_benchmark/benchmarks.py`) and is recorded as such
> rather than invoked with a flag it cannot honor.

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
| claude | mmlu | 12/12 | 12/12 | 0 |
| claude | humaneval | 6/12 | 8/12 | +2 |
| claude | hellaswag | 8/8 | 8/8 | 0 |
| claude | truthfulqa | 8/8 | 8/8 | 0 |
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
| 2026-07-10T21-26-52 | +1,718 | — | — | 36/40 | — | — |
