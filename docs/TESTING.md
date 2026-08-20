# Testing

> How to run the bats and pytest suites.

**Last Updated**: 2026-08-20

## Testing

```bash
# Python tests (full suite: agents/ package, orchestrator scripts)
pytest tests/python/ -q

# Shell tests (full Bats suite covering bootstrap and scripts)
npx bats tests/bats/

# Lint shell scripts
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh

# Validate YAML configs
yamllint configs/claude/config/*.yml
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
```

CI runs on every push via GitHub Actions (`.github/workflows/ci.yml`).

---

---

[← Manifest README](../README.md)
