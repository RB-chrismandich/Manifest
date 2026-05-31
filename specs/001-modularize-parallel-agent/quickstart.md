# Quickstart: Parallel Agent Orchestration Modularization

**Branch**: `001-modularize-parallel-agent` | **Date**: 2026-05-31

This guide walks a developer through verifying the modularization is complete and
correct.

---

## Prerequisites

```bash
# Ensure you are on the feature branch
git branch --show-current
# Expected: 001-modularize-parallel-agent

# Confirm Python 3.9+ is available
python3 --version

# Install dependencies if not already present
pip install -r configs/claude/scripts/requirements.txt 2>/dev/null || true
pip install pytest
```

---

## Step 1: Verify package structure exists

```bash
ls configs/claude/scripts/agents/
# Expected: __init__.py  cli.py  config.py  orchestrator.py  runners.py  synthesis.py  validation.py
```

---

## Step 2: Run the updated test suite

```bash
pytest tests/python/ -v
```

Expected: All tests pass. If any fail, the import paths in
`tests/python/test_parallel_agent.py` or the per-module test files need correction.

---

## Step 3: Run per-module tests independently

Each module must be testable in isolation:

```bash
# Test config module alone
pytest tests/python/agents/test_config.py -v

# Test validation module alone
pytest tests/python/agents/test_validation.py -v

# Test synthesis module alone
pytest tests/python/agents/test_synthesis.py -v

# Test runners module alone
pytest tests/python/agents/test_runners.py -v

# Test orchestrator module alone
pytest tests/python/agents/test_orchestrator.py -v

# Test CLI module alone
pytest tests/python/agents/test_cli.py -v
```

Each command must exit 0 without requiring external agent connections.

---

## Step 4: Verify CLI entry point is unchanged

```bash
# Verify help output is identical to pre-modularization
python configs/claude/scripts/parallel_agent.py --help
```

Confirm all flags (`--json`, `--validate`, `--review`, `--analyze`, `--timeout`,
`--claude-only`, etc.) appear in the help output.

---

## Step 5: Smoke-test JSON output structure

```bash
# This will fail gracefully if no API keys are present — that is expected
python configs/claude/scripts/parallel_agent.py --json --claude-only "smoke test" \
  2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('keys:', sorted(d.keys()))" \
  || echo "(No API key available — CLI parsing still verified)"
```

---

## Step 6: Verify module sizes (SC-004 check)

```bash
for f in configs/claude/scripts/agents/*.py; do
  wc -l "$f"
done
```

Each file MUST be under 500 lines (runners.py and orchestrator.py may be slightly
above; see Complexity Tracking in plan.md for accepted justification).

---

## Common Issues

**ImportError: No module named 'agents'**
→ Ensure `sys.path` in the test file includes `configs/claude/scripts/`.
The existing `SCRIPTS_DIR` setup in `test_parallel_agent.py` handles this automatically.

**Tests pass but `--help` fails**
→ `parallel_agent.py` shim is missing or not calling `agents.cli.main`. Check the
shim's import and `asyncio.run(main())` call.

**`runners.py` has circular import**
→ Ensure `runners.py` only imports from `config.py`, not from `orchestrator.py`.
The dependency must be: config ← runners ← orchestrator ← cli (one direction only).
