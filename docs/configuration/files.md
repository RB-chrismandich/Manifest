# Files, Precedence & Environment

> Which file wins, and which env vars override it.

**Last Updated**: 2026-08-20

## Configuration Files

All configuration files are located in `~/.claude/config/`:

| File | Purpose | Format |
|------|---------|--------|
| `services.yml` | Agent enable/disable states | YAML |
| `command_config.yml` | Tool policies, thresholds, model defaults | YAML |
| `validation_criteria.yml` | Tier 1/2 security and quality rules | YAML |
| `skillclaw.yml` | SkillClaw storage, ingest, evolve, and promotion settings | YAML |

### File Locations

```bash
# View configuration directory
ls -la ~/.claude/config/

# Edit configurations
vim ~/.claude/config/services.yml
vim ~/.claude/config/command_config.yml
vim ~/.claude/config/validation_criteria.yml
vim ~/.claude/config/skillclaw.yml
```

### Claude Code Session Settings (`settings.local.json`)

The deployed `~/.claude/settings.local.json` carries Claude Code session settings
in addition to permissions, hooks, and MCP servers:

| Key | Value | Purpose |
|-----|-------|---------|
| `skillListingBudgetFraction` | `0.05` | Fraction of the context window reserved for the auto-loaded skill name/description listing. Manifest ships 70+ skills, so the Claude Code default (`0.01`) collapses many descriptions to name-only and weakens skill triggering; `0.05` keeps more descriptions visible. Requires Claude Code v2.1.105+. |

Bootstrap unions this default into an **existing** `settings.local.json`
(`merge_claude_settings_defaults`) **user-wins** — a value you set yourself is
never overwritten, so `vim` your own `skillListingBudgetFraction` and it survives
the next `./bootstrap.sh`.

#### Optional: 1-hour prompt caching (opt-in, not deployed)

`ENABLE_PROMPT_CACHING_1H=1` opts Claude Code into the 1-hour prompt-cache TTL
(vs. the 5-minute default). It is **not** deployed by Manifest for two reasons:

- It only takes effect as a **shell environment variable read before `claude`
  launches** — the `settings.json` `env` block reaches spawned subprocesses, not
  Claude Code's own runtime, so setting it there is a silent no-op.
- On a **Claude subscription the 1-hour TTL is already the free default**; the
  variable only changes behavior on **API-key / Bedrock / third-party**
  providers, where the longer TTL bills cache writes at a **higher rate**. That
  cost trade-off is a per-user choice, not a blanket default.

Enable it yourself when you want it:

```bash
# Persist for every session (zsh; use ~/.bashrc for bash)
echo 'export ENABLE_PROMPT_CACHING_1H=1' >> ~/.zshrc

# Or one launch only
ENABLE_PROMPT_CACHING_1H=1 claude
```

---

## Override Precedence

Configuration values are resolved in this order (highest to lowest priority):

1. **CLI Arguments** (highest priority)
   - `--cursor-model advanced`
   - `--timeout 900`
   - `--no-claude`

2. **Environment Variables**
   - `CURSOR_MODEL_ADVANCED=gpt-5.2`
   - `GEMINI_INCLUDE_DIRS=/path`

3. **Configuration Files**
   - `~/.claude/config/services.yml`
   - `~/.claude/config/command_config.yml`

4. **Hardcoded Defaults** (lowest priority)
   - Built into `parallel_agent.py`

**Example Resolution:**

```bash
# Command
~/.claude/scripts/parallel_agent.py --cursor-model flash --timeout 300 "Task"

# services.yml says cursor disabled, but --cursor-model enables it
# command_config.yml says timeout=600, but --timeout overrides to 300
# Final: Cursor runs with flash model, 300s timeout
```

---

## Environment Variables

Override defaults without modifying configuration files.

### Gemini Configuration

```bash
# Colon-separated directories to include in Gemini context
export GEMINI_INCLUDE_DIRS="$(pwd):~/.claude:~/.gemini:/path/to/other/dir"
```

### Model Tier Mappings

```bash
# Cursor models
export CURSOR_MODEL_MINI="gpt-5.1-codex-mini"
export CURSOR_MODEL_FLASH="gpt-5.1-codex"
export CURSOR_MODEL_ADVANCED="gpt-5.2"

# Gemini models
export GEMINI_MODEL_FLASH="gemini-3-flash-preview"
export GEMINI_MODEL_PRO="gemini-3-pro-preview"
```

### Provider API Keys (Optional)

```bash
# When set (and the SDK package is installed), Claude/Gemini run via the SDK.
# When unset, they fall back to the logged-in `claude` / `gemini` CLIs (OAuth).
export ANTHROPIC_API_KEY="sk-ant-..."   # Claude SDK backend
export GOOGLE_API_KEY="AIza..."         # Gemini SDK backend
```

### Model Pin Verification

```bash
# Live one-shot CLI probe per claude/gemini pin (one tiny LLM call each) —
# use on OAuth-only machines where no API key is available to list models
MODEL_CHECK_PROBE=1 ~/.claude/scripts/model_check.sh

# Override the probe binaries (e.g. test doubles)
export MODEL_CHECK_CLAUDE_BIN="claude"
export MODEL_CHECK_GEMINI_BIN="gemini"
```

### Spec Review Configuration

```bash
# Override the reviewer model (default: resolves model_tiers.antigravity.advanced via agy)
export SPEC_REVIEW_MODEL="gemini-3-pro-preview"

# Override the config file passed to spec_review.sh
export SPEC_REVIEW_CONFIG="~/.claude/config/parallel_agent.yml"
```

### Feature Flags

```bash
# Enable pre-flight credit check before running agents
export CHECK_CREDITS_PREFLIGHT="true"
```

---

---

[← Configuration](README.md)
