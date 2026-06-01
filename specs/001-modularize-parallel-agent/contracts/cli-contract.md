# Contract: CLI Interface

**Module**: `agents/cli.py` via `parallel_agent.py` entry point
**Type**: Command-line interface contract
**Status**: Preserved unchanged — this contract is the regression gate for SC-003.

---

## Invocation

```
python parallel_agent.py [OPTIONS] [PROMPT]
```

The `parallel_agent.py` entry point MUST remain the canonical invocation path. All
flags, positional arguments, output formats, and exit codes defined below MUST be
identical before and after modularization.

---

## Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `PROMPT` | positional (optional) | The prompt string to send to all agents |

## Flags (verified against current implementation)

| Flag | Description |
|------|-------------|
| `--json` | Output results as JSON |
| `--full-output` | Include full agent responses in output |
| `--validate` | Run Tier 1 + Tier 2 validation on agent outputs |
| `--review FILE` | Review a specific file (sets mode=review) |
| `--analyze FILE` | Analyze a specific file (sets mode=analyze) |
| `--timeout SECONDS` | Per-agent timeout in seconds |
| `--cursor-only` | Run only Cursor agent |
| `--gemini-only` | Run only Gemini agent |
| `--claude-only` | Run only Claude agent |
| `--codex-only` | Run only Codex agent |
| `--claude-model MODEL` | Override Claude model (haiku/sonnet/opus) |
| `--cursor-model MODEL` | Override Cursor model (mini/advanced) |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — all agents responded |
| 1 | Error — at least one agent failed or invalid arguments |

## Output Format (--json mode)

The JSON schema produced by `--json` MUST be identical before and after modularization.
Structure includes: `agents` array, `consensus_score`, `verdict`, `synthesis` (if
triggered), `validation` (if `--validate`), `timestamp`, `duration_seconds`.

---

## Behavioral Equivalence Verification

Before starting modularization, capture a baseline:

```bash
# Capture current output structure (mocked; no live agents needed)
python parallel_agent.py --json --claude-only "smoke test" 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.keys()))"
```

After modularization, run the same command and assert the top-level JSON keys are
identical. Additionally run:

```bash
pytest tests/python/test_parallel_agent.py -v
```

All tests must pass with exit code 0.
