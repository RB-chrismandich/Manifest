---
name: token-benchmark
description: |
  Measure input/output token overhead and quality delta introduced by Manifest config
  deployment across Claude, Gemini CLI, and Antigravity CLI. Runs 20 industry-standard
  benchmark prompts (MMLU, HumanEval, HellaSwag, TruthfulQA) before and after manifest
  context injection via isolated HOME directories, then regenerates docs/TOKEN_BENCHMARK.md.
---

# Token Benchmark Skill

Measure how the Manifest configs affect token costs and response quality per CLI provider.

## Prerequisites

Check that the following are available before running. Report any missing items and stop.

```bash
# API keys
echo "${ANTHROPIC_API_KEY:+claude api key: set}" || echo "ANTHROPIC_API_KEY: missing"
echo "${GOOGLE_API_KEY:+gemini api key: set}" || echo "GOOGLE_API_KEY: missing (or use OAuth)"

# CLI binaries
command -v claude    && echo "claude binary: ok"    || echo "claude binary: missing"
command -v gemini    && echo "gemini binary: ok"    || echo "gemini binary: missing"
command -v agy       && echo "agy binary: ok"       || echo "agy binary: missing (antigravity)"

# Python packages
python3 -c "import anthropic; print(f'anthropic {anthropic.__version__}: ok')" 2>/dev/null || echo "anthropic package: missing — pip install anthropic"
python3 -c "from google import genai; print('google-genai: ok')" 2>/dev/null || echo "google-genai package: missing — pip install google-genai"
```

If any API key or binary is missing, inform the user and offer to run with `--api-only` (skips CLI path) or `--providers claude` (single provider).

## Arguments

Parse `$ARGUMENTS` for flags. Supported flags:

| Flag | Effect |
|------|--------|
| (none) | Full run: all providers, API + CLI paths |
| `--providers claude` | Only Claude (faster, ~3 min) |
| `--providers claude,gemini` | Claude + Gemini, no Antigravity |
| `--sync-fixtures` | Sync `fixtures/manifest/` from live `~/.claude` etc. first |
| `--api-only` | Skip CLI behavioral tests; API token counts only |
| `--report-only` | Regenerate `docs/TOKEN_BENCHMARK.md` from existing results; no new API calls |

## Execution

Run the harness from the repo root:

```bash
# Parse flags from $ARGUMENTS; default to all providers + both paths
PROVIDERS="${PROVIDERS:-claude,gemini,antigravity}"
API_ONLY_FLAG="${API_ONLY_FLAG:-}"
SYNC_FLAG="${SYNC_FLAG:-}"

# Set vars from $ARGUMENTS
echo "$ARGUMENTS" | grep -q -- "--sync-fixtures" && SYNC_FLAG="--sync-fixtures"
echo "$ARGUMENTS" | grep -q -- "--api-only"       && API_ONLY_FLAG="--api-only"
echo "$ARGUMENTS" | grep -qP -- "--providers\s+(\S+)" && \
  PROVIDERS=$(echo "$ARGUMENTS" | grep -oP '(?<=--providers\s)\S+')
echo "$ARGUMENTS" | grep -q -- "--report-only" && exec python3 tests/token_benchmark/harness.py --report-only

python3 tests/token_benchmark/harness.py \
  --providers "$PROVIDERS" \
  $SYNC_FLAG \
  $API_ONLY_FLAG
```

## After the run

1. Print the summary table from `docs/TOKEN_BENCHMARK.md` (the `## Token Overhead` section).
2. Ask: "Commit the updated TOKEN_BENCHMARK.md? (y/n)"
3. If yes:
```bash
git add docs/TOKEN_BENCHMARK.md tests/token_benchmark/results/
git commit -m "chore: update token benchmark results $(date +%Y-%m-%d)"
```

## Expected runtime

- Full run (all providers, API + CLI): ~8–15 minutes (20 prompts × 2 conditions × 3 providers)
- API-only (2 providers): ~4–6 minutes
- Single provider: ~2–3 minutes
