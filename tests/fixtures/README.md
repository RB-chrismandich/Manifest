# Test Fixtures

Mock data and test fixtures for Manifest's test suites.

## Structure

- `mock_agent_output.json` -- Sample parallel agent JSON output for testing synthesis/validation
- `mock_config.yml` -- Sample configuration for testing YAML parsing
- `agent_roster_synthetic.yml` -- The 5 real agents (claude, gemini, cursor,
  codex, antigravity) from `agent_roster.yml`, shared by
  `tests/python/agents/test_runner_generic.py` and
  `tests/python/test_reconcile_policy.py`; each appends its own distinct
  synthetic 6th-agent block (differing values are load-bearing per test, so
  they stay inline rather than merging into this file)

## Usage

Fixtures are loaded by test files in `../bats/` and `../python/` via relative paths.
