# Configuration Basics

> The few settings worth changing before you go further.

## Configuration Basics

### Enable/Disable Services

Services are configured in `~/.claude/config/services.yml`:

```yaml
services:
  claude:
    enabled: true  # Enable/disable Claude CLI
  gemini:
    enabled: true  # Enable/disable Gemini CLI
  cursor:
    enabled: true  # Enable/disable Cursor Agent
  codex:
    enabled: true  # Enable/disable Codex CLI
  antigravity:
    enabled: true  # Enable/disable Antigravity CLI (agy)
  devin:
    enabled: false  # Devin CLI — opt-in; needs `devin auth login`
  git_cli:
    github:
      enabled: auto  # auto | true | false (auto-detect if installed)
    gitlab:
      enabled: auto  # auto | true | false (auto-detect if installed)
```

**Reconfigure after initial setup:**

```bash
# Disable Cursor Agent
./bootstrap.sh --reconfigure --disable-cursor

# Re-enable Gemini CLI
./bootstrap.sh --reconfigure --enable-gemini

# Enable Git CLIs explicitly
./bootstrap.sh --reconfigure --enable-gh --enable-glab
```

### Model Selection

Choose models based on task complexity:

```bash
# Security analysis (use most powerful models)
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Quick queries (use lightweight models)
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "Quick question"
```

**Model tiers:**

| Tier | Cursor | Claude | Gemini | Codex | Antigravity | Use For |
|------|--------|--------|--------|-------|-------------|---------|
| Lightweight | cursor-grok-4.5-low | claude-haiku-4-5 | - | gpt-5.6-luna | gemini-3.6-flash-low | Quick questions |
| Balanced | cursor-grok-4.5-medium | claude-sonnet-5 | gemini-3-flash-preview | gpt-5.6-terra | gemini-3.6-flash-high | Code review |
| Maximum | cursor-grok-4.5-high | claude-opus-5 | gemini-3-pro-preview | gpt-5.6-sol | claude-opus-4-6-thinking | Security analysis |

Verified 2026-07-29 by a live one-shot call per pin, **except** the Gemini and
Codex columns: the `gemini` CLI is ineligible on a free-tier account (migrate to
Antigravity) and the `codex` CLI is logged out, so neither could be confirmed.
See [CONFIGURATION.md](CONFIGURATION.md#model-tiers) for per-provider status.

Devin is absent from this table on purpose: its catalog is login-gated, so nothing
is pinned. `--devin-model` defaults to `auto` (no `--model` flag) and otherwise
passes your value through verbatim.

**See**: [Configuration Guide](../configuration/README.md) for all options

### Consensus Thresholds

Agents agree when consensus score ≥ threshold:

- **≥80%**: High confidence → auto-proceed with unified recommendation
- **50-79%**: Medium confidence → highlight disagreements to user
- **<50%**: Low confidence → escalate for human review

Configure in `~/.claude/config/command_config.yml`:

```yaml
# float 0.0-1.0 scale — must match command_config.yml
consensus:
  high: 0.80
  medium: 0.50
  low: 0.0
```

---

---

[← Getting Started](../GETTING_STARTED.md)
