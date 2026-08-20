# Configuration Quickstart

> The settings most people change first.

## Configuration

### Enable/Disable Services

```bash
# Reconfigure after initial setup
./bootstrap.sh --reconfigure --disable-cursor
./bootstrap.sh --reconfigure --enable-gemini --disable-claude
./bootstrap.sh --reconfigure --disable-codex

# Enable SkillClaw session capture (opt-in; default: disabled)
./bootstrap.sh --reconfigure --enable-skillclaw

# Enable Git CLIs explicitly
./bootstrap.sh --reconfigure --enable-gh --enable-glab

# Configure MCP servers (interactive per-server selection; --force to auto-accept all)
./bootstrap.sh --install-mcp
```

The "Services to configure" banner and end-of-run summary reflect the effective
configuration (existing `~/.claude/config/services.yml` merged with explicit CLI flags).

### Model Selection

```bash
# Use advanced models for security analysis
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Use lightweight models for quick queries
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

Model tiers map to concrete pins in `~/.claude/config/parallel_agent.yml` (`model_tiers`),
e.g. Gemini `flash`/`pro` → `gemini-3-flash-preview` / `gemini-3-pro-preview`. Verify pins
against live provider listings with `model_check.sh` (add `MODEL_CHECK_PROBE=1` for a
one-shot CLI probe per pin on OAuth-only machines without API keys).

**See**: [Configuration Guide](../../docs/configuration/README.md) for complete YAML reference, environment
variables, and advanced options

---

---

[← Manifest README](README.md)
