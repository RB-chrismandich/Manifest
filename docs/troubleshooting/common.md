# Common Problems

> The failures new users hit most often.

**Last Updated**: 2026-08-20

## Troubleshooting

**Bootstrap fails with "Permission denied":**

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

**Agents not running:**

```bash
# Check service configuration
cat ~/.claude/config/services.yml

# Verify CLI tools installed
which claude gemini cursor codex
```

**Model pins reported as unverified by check_status.sh:**

```bash
# Symptom: "N check(s) unverified (no API credentials ...)"
# On OAuth-only machines there are no API keys to list models with, so
# check_status.sh reports the pins as unverified rather than falsely green.
# Live-verify each pin with a one-shot CLI probe (one tiny LLM call per pin):
MODEL_CHECK_PROBE=1 ~/.claude/scripts/model_check.sh
```

**Codex fails with session permission errors:**

```bash
# Symptom from parallel_agent.py/check_status.sh:
# "Codex session storage not writable: ~/.manifest/codex/sessions"

# Preferred fix (restore ownership/permissions)
sudo chown -R "$(whoami)" ~/.manifest
chmod -R u+rwX ~/.manifest
```

```bash
# Optional override: move Codex state to a custom path
mkdir -p ~/.manifest/custom-codex-state
export CODEX_HOME="$HOME/.manifest/custom-codex-state"

# Then run orchestration as normal
~/.claude/scripts/parallel_agent.py --codex-only --codex-model advanced "Quick test"
```

**See**: [Troubleshooting Guide](../../docs/troubleshooting/README.md) for 15+ common issues with solutions

---

---

[← Troubleshooting](README.md)
