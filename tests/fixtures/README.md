# Test Fixtures

Mock data and test fixtures for Manifest's test suites.

## Structure

- `mock_agent_output.json` -- Sample parallel agent JSON output for testing synthesis/validation
- `mock_config.yml` -- Sample configuration for testing YAML parsing

## Usage

Fixtures are loaded by test files in `../bats/` and `../python/` via relative paths.
