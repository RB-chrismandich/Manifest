---
name: token-benchmark
description: Measure token overhead and quality delta from Manifest config across Claude, Gemini CLI, and Antigravity CLI using MMLU/HumanEval/HellaSwag/TruthfulQA prompts before/after manifest context injection; regenerates docs/TOKEN_BENCHMARK.md.
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

# Python packages (uv-managed via the `benchmark` dependency group — #547).
# Only relevant to the API path (claude/gemini); skip entirely for a --cli-only run
# (e.g. antigravity), which needs neither uv nor these SDKs.
if command -v uv >/dev/null 2>&1; then
  uv run --group benchmark python -c "import anthropic; print(f'anthropic {anthropic.__version__}: ok')" 2>/dev/null || echo "anthropic: missing — check [dependency-groups].benchmark in pyproject.toml"
  uv run --group benchmark python -c "from google import genai; print('google-genai: ok')" 2>/dev/null || echo "google-genai: missing — check [dependency-groups].benchmark in pyproject.toml"
else
  echo "uv: missing — required only for the API path (claude/gemini); not needed for --cli-only"
fi
```

If any API key or binary is missing, inform the user and offer to run with `--api-only` (skips CLI path) or
`--providers claude` (single provider). The harness itself hard-fails (exit 2, no rows
written) if the API path is requested without its SDK importable; `--cli-only` and `--report-only`
need no SDK and no `uv` — the execution step below only invokes `uv run` when the API path is
actually in play.

> **Antigravity caveat**: `agy` has no SDK and no verified `--system-prompt` mechanism (see
> `PROVIDER_CLI_CONFIG` in `tests/token_benchmark/benchmarks.py`), so it is **unsupported/quality-only**
> in this benchmark — it never produces Token-Overhead or Cost numbers, only (currently
> `unsupported`) CLI rows, rendered as such in `docs/TOKEN_BENCHMARK.md` rather than silently
> dropped. Do not build a tokenizer or a PRICING entry for it; that is out of scope by design.

## Arguments

Parse `$ARGUMENTS` for flags. The table mirrors the harness argparse
(`tests/token_benchmark/harness.py`) — keep them in sync (#548):

| Flag | Effect | Default |
|------|--------|---------|
| (none) | Full run: all providers, API + CLI paths | — |
| `--providers <list>` | Comma-separated providers to run (e.g. `claude` alone is ~3 min) | `claude,gemini,antigravity` |
| `--api-only` | Skip the CLI path; API token/cost counts only (claude, gemini) | off |
| `--cli-only` | Skip the API path; run only the CLI behavioral/quality path — the only viable path for CLI-only providers with no SDK (e.g. `antigravity`) | off |
| `--sync-fixtures` | Sync `fixtures/manifest/` (and `fixtures-compressed/` if `--compression` given) from the live home before running | off |
| `--compression <N>` | With `--sync-fixtures`: also write `fixtures-compressed/` keeping the first N% of `CLAUDE.md` lines | unset |
| `--report-only` | Regenerate `docs/TOKEN_BENCHMARK.md` from existing `results/*.jsonl`; no new API/CLI calls | off |
| `--claude-model <id>` | Claude model id used for the API path | `claude-sonnet-4-6` |
| `--gemini-model <id>` | Gemini model id used for the API path | `gemini-3-flash-preview` |
| `--conditions <list>` | Comma-separated conditions: `before,after,cached,tiered,compressed` | `before,after` |

## Execution

Run the harness from the repo root:

```bash
# Parse flags from $ARGUMENTS; default to all providers + both paths
PROVIDERS="${PROVIDERS:-claude,gemini,antigravity}"
API_ONLY_FLAG="${API_ONLY_FLAG:-}"
CLI_ONLY_FLAG="${CLI_ONLY_FLAG:-}"
SYNC_FLAG="${SYNC_FLAG:-}"

# Set vars from $ARGUMENTS
echo "$ARGUMENTS" | grep -q -- "--sync-fixtures" && SYNC_FLAG="--sync-fixtures"
echo "$ARGUMENTS" | grep -q -- "--api-only"       && API_ONLY_FLAG="--api-only"
echo "$ARGUMENTS" | grep -q -- "--cli-only"       && CLI_ONLY_FLAG="--cli-only"
echo "$ARGUMENTS" | grep -qP -- "--providers\s+(\S+)" && \
  PROVIDERS=$(echo "$ARGUMENTS" | grep -oP '(?<=--providers\s)\S+')
echo "$ARGUMENTS" | grep -q -- "--report-only" && exec python3 tests/token_benchmark/harness.py --report-only

# Only invoke `uv run --group benchmark` for runs that actually touch the API path.
# --cli-only and --report-only are SDK-free by design (#547) and must stay runnable
# with a plain `python3` — no uv resolution/installation, no uv dependency at all.
if [ -n "$CLI_ONLY_FLAG" ]; then
  PYRUN="python3"
else
  PYRUN="uv run --group benchmark python"
fi

$PYRUN tests/token_benchmark/harness.py \
  --providers "$PROVIDERS" \
  $SYNC_FLAG \
  $API_ONLY_FLAG \
  $CLI_ONLY_FLAG
```

`--cli-only` is the only viable path for a CLI-only provider with no API SDK: pass
`--providers antigravity --cli-only` to run just its (currently `unsupported`) quality path
without touching claude/gemini's API path — and without requiring `uv` to be installed.

## After the run

1. Print the summary table from `docs/TOKEN_BENCHMARK.md` (the `## Token Overhead` section).
2. Ask: "Commit the updated TOKEN_BENCHMARK.md? (y/n)"
3. If yes:

```bash
# --sync-fixtures modifies tests/token_benchmark/fixtures/ in the working
# tree, so include it — otherwise the committed fixtures drift stale.
git add docs/TOKEN_BENCHMARK.md tests/token_benchmark/results/ tests/token_benchmark/fixtures/
git commit -m "chore: update token benchmark results $(date +%Y-%m-%d)"
```

## Expected runtime

- Full run (all providers, API + CLI): ~8–15 minutes (20 prompts × 2 conditions × 3 providers)
- API-only (2 providers): ~4–6 minutes
- Single provider: ~2–3 minutes
