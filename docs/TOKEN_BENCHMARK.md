# Token Benchmark Report

**Last run**: 2026-06-13
**Prompts**: 20 (6 MMLU, 6 HumanEval, 4 HellaSwag, 4 TruthfulQA)

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
| claude | 27 | 24 | -3 |
| gemini | — | — | — |

## Quality Scores (CLI — correct / total)

| Provider | Category | Before | After | Delta |
|----------|----------|--------|-------|-------|
| claude | mmlu | — | — | — |
| claude | humaneval | — | — | — |
| claude | hellaswag | — | — | — |
| claude | truthfulqa | — | — | — |
| gemini | mmlu | — | — | — |
| gemini | humaneval | — | — | — |
| gemini | hellaswag | — | — | — |
| gemini | truthfulqa | — | — | — |
| antigravity | mmlu | — | — | — |
| antigravity | humaneval | — | — | — |
| antigravity | hellaswag | — | — | — |
| antigravity | truthfulqa | — | — | — |

## Historical Runs

| Run ID | Claude Input Overhead | Gemini Input Overhead | Claude Quality | Gemini Quality |
|--------|-----------------------|-----------------------|----------------|----------------|
| 2026-06-13T06-58-25 | +1,718 | — | — | — |
