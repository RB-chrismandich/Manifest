# Configuration Guide

> Comprehensive reference for all Manifest configuration options

**Last Updated**: 2026-06-12
**Audience**: System operators, advanced users
**Prerequisites**: Manifest installed via bootstrap.sh or manually

---

## Table of Contents

1. [Configuration Files](#configuration-files)
2. [Service Configuration](#service-configuration)
3. [SkillClaw Configuration (Optional)](#skillclaw-configuration-optional)
4. [Command Configuration](#command-configuration)
5. [Validation Criteria](#validation-criteria)
6. [Model Selection](#model-selection)
7. [Environment Variables](#environment-variables)
8. [CLI Agent Command Configuration](#cli-agent-command-configuration)
9. [Command-Line Options](#command-line-options)
10. [Override Precedence](#override-precedence)

---

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

---

## Service Configuration

**File**: `~/.claude/config/services.yml`

Controls which AI agents are enabled for parallel orchestration.

### Structure

```yaml
services:
  # Claude Code CLI - Anthropic's AI assistant
  claude:
    enabled: true  # Set to false to disable
    command: claude
    description: "Deep reasoning, security analysis, complex logic"
    model_tiers:
      - haiku    # Fast, economical
      - sonnet   # Balanced (default)
      - opus     # Maximum capability

  # Gemini CLI - Google's AI assistant
  gemini:
    enabled: true
    command: gemini
    description: "Broad knowledge, creative solutions, research"
    model_tiers:
      - flash    # Fast (default)
      - pro      # Advanced

  # Cursor Agent - IDE-integrated AI
  cursor:
    enabled: true
    command: cursor
    description: "IDE-integrated context, code-specific analysis"
    model_tiers:
      - mini     # Lightweight
      - flash    # Balanced (default)
      - advanced # Maximum capability

  # Codex CLI - OpenAI terminal coding agent
  codex:
    enabled: true
    command: codex
    description: "Terminal coding assistant for codebase edits and automation"
    model_tiers:
      - mini     # Lightweight (gpt-5.4-mini)
      - flash    # Balanced (gpt-5.4, default)
      - advanced # Maximum capability (gpt-5.5)
      - auto     # Use Codex config default model

  # Git CLI tools - Platform-specific Git hosting integrations
  git_cli:
    github:
      enabled: auto  # auto | true | false (default: auto-detect)
      command: gh
      description: "GitHub CLI for issue/PR management"
    gitlab:
      enabled: auto  # auto | true | false (default: auto-detect)
      command: glab
      description: "GitLab CLI for issue/MR management"
    detection:
      platform: auto  # auto | github | gitlab | git
      remote: origin  # overridable via MANIFEST_GIT_REMOTE

# Minimum agents required for parallel orchestration
minimum_agents: 2

# Fallback behavior when enabled services are unavailable
fallback:
  strategy: continue_with_available  # Options: continue_with_available, abort, warn_user
  warn_threshold: 1  # Warn if only this many agents available
```

### Enabling/Disabling Services

### Option 1: Reconfigure with bootstrap.sh

```bash
# Disable Cursor
./bootstrap.sh --reconfigure --disable-cursor

# Enable all services
./bootstrap.sh --reconfigure --enable-claude --enable-gemini --enable-cursor

# Enable Git CLIs explicitly (useful when auto-detect isn't desired)
./bootstrap.sh --reconfigure --enable-gh --enable-glab

# Disable Git CLIs
./bootstrap.sh --reconfigure --disable-gh --disable-glab

# Enable browser-use (Python E2E browser automation for /browser-test)
./bootstrap.sh --reconfigure --enable-browser-use
```

### Option 2: Edit services.yml manually

```bash
# Edit configuration
vim ~/.claude/config/services.yml

# Change enabled: true to enabled: false
services:
  cursor:
    enabled: false  # Disabled
```

### Option 3: Override at runtime with CLI flags

```bash
# Temporarily disable Claude for this run only
~/.claude/scripts/parallel_agent.py --no-claude "Task"

# Run only Cursor Agent
~/.claude/scripts/parallel_agent.py --cursor-only "Task"
```

### Service Validation

The script validates services on startup:

1. Checks if `services.yml` exists
2. Parses enabled/disabled state for each service
3. Verifies minimum agent count (default: 2)
4. Warns if fewer agents than minimum are available

---

## SkillClaw Configuration (Optional)

**File**: `~/.claude/config/skillclaw.yml`
**Repo source**: `configs/claude/config/skillclaw.yml`

SkillClaw is an **opt-in**, proxy-free skill evolution pipeline. It passively reads
`~/.claude/projects/**/*.jsonl` transcripts (the same files Claude Code writes during
normal sessions), evolves them into skill candidates using `claude -p` (Max-backed,
no separate API key required), and opens review PRs. It is **disabled by default** and
does not intercept any agent traffic — no daemon is started, no shell wrappers are
installed, no `BASE_URL` environment variable is set.

### Enabling and Disabling

```bash
# Enable SkillClaw (creates chmod-700 storage dirs; no daemon or wrappers)
./bootstrap.sh --enable-skillclaw

# Disable SkillClaw
./bootstrap.sh --disable-skillclaw

# Reconfigure alongside other toggles
./bootstrap.sh --reconfigure --enable-skillclaw --disable-cursor
```

When enabled, `services.yml` gains a `skillclaw:` stanza set to `enabled: true`.

### What skillclaw.yml Configures

`~/.claude/config/skillclaw.yml` is the **Manifest-owned** config. It is distinct from
the vestigial upstream `~/.skillclaw/config.yaml` that older versions of the skillclaw
tool may create.

```yaml
# Storage — session and evolved-skill data (chmod 700; secrets scrubbed before evolution)
storage:
  root: ~/.skillclaw
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/skills
  rejected: ~/.skillclaw/skills/rejected
  state: ~/.skillclaw/.ingest-state.json

# Ingest — how transcripts are read from ~/.claude/projects
ingest:
  transcripts_dir: ~/.claude/projects
  window_days: 30              # only transcripts modified within the last 30 days
  settle_minutes: 5            # skip files whose mtime is <5 min old (still being written)
  max_tool_output_chars: 500   # truncate tool stdout/stderr incl. base64 blobs (noise control)

# Evolve — how ingested sessions become skill candidates
evolve:
  engine: claude-cli            # `claude -p` headless, Max-backed; no separate API key
  token_budget: 100000          # map-reduce chunk threshold; stays clear of 200k context limit
  prompt_template: ~/.claude/prompts/skillclaw_evolve.md

# Promotion — how evolved skills become PRs
promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels:
    - needs-review
    - follow-up
```

### How It Works

1. **Ingest** (`skillclaw_ingest.py`) scans `~/.claude/projects/**/*.jsonl` for transcripts
   within the `window_days` window, skipping files still being written (`settle_minutes`).
   Tool output is truncated to `max_tool_output_chars` characters to reduce noise.
2. **Evolve** (`skillclaw_evolve.py`) runs `claude -p` in map-reduce mode against each
   ingested session, staying under the `token_budget` threshold to avoid the 200 k context
   limit. Candidates that pass quality checks are written to `evolved/`; rejected ones go to
   `rejected/` for inspection.
3. **Promote** (`skillclaw_promote.sh`, also `/skill-evolve`) opens one review PR per run.

### Promotion

Evolved skills are promoted via `~/.claude/scripts/skillclaw_promote.sh` (also available as
the `/skill-evolve` slash command). Dry-run is the default; pass `--apply` to open a PR.
The script opens one review PR (one commit per skill) and aborts if an open
`skillclaw/evolve-*` PR already exists — use `--force-new` to override.

**Full design doc**: [docs/SKILLCLAW.md](SKILLCLAW.md)

---

## Command Configuration

**File**: `~/.claude/config/command_config.yml`

Defines behavior for each slash command.

### Thresholds

```yaml
thresholds:
  # Documentation commands
  improve_docs_lines: 500         # Trigger parallel agents when total doc lines > 500
  generate_diagrams_modules: 5    # Trigger when analyzing 5+ unique imports/modules

  # Code quality skill auto-triggers
  skill_file_lines: 500           # File > 500 lines
  skill_function_count: 10        # > 10 functions per file
  skill_class_count: 5            # > 5 classes per file
  skill_cyclomatic_complexity: 15 # Cyclomatic complexity > 15
```

### Consensus Thresholds

```yaml
consensus:
  high: 80      # >=80%: Auto-proceed with unified recommendation
  medium: 50    # 50-79%: Highlight disagreements to user
  low: 0        # <50%: Block and escalate for human review
```

**Example**: If 2 of 3 agents agree → 67% consensus → medium confidence → disagreements highlighted

### Tool Policies

Defines which tools each command can use:

```yaml
tool_policies:
  refactor-python:
    allowed:
      - Read
      - Glob
      - Grep
    forbidden:
      - Bash
      - Write
      - Edit  # Read-only analysis
    parallel_agents: always
    validation_tier: 1

  docs-diagrams:
    allowed:
      - Read
      - Glob
      - Grep
    forbidden:
      - Bash
    parallel_agents: conditional
    trigger_condition: unique_imports >= 5
    validation_tier: 2
```

**Parallel agent modes:**

- `always`: Always run parallel agents
- `never`: Never run parallel agents (single-agent mode)
- `conditional`: Run based on trigger_condition

### Model Selection Defaults

```yaml
task_model_defaults:
  security:
    cursor: advanced
    claude: opus
    gemini: pro
    reason: "Security-critical code requires maximum model capability"

  review:
    cursor: flash
    claude: sonnet
    gemini: flash
    reason: "Code review benefits from balanced capability/speed"

  analyze:
    cursor: flash
    claude: sonnet
    gemini: flash
    reason: "Analysis tasks need good reasoning without opus cost"

  quick:
    cursor: mini
    claude: haiku
    gemini: flash
    reason: "Quick queries use lightest models for speed"
```

### Credit Exhaustion Fallback

```yaml
credit_fallback:
  cursor:
    chain:
      - advanced       # Try gpt-5.2 first
      - flash          # Fall back to gpt-5.1-codex
      - mini           # Fall back to gpt-5.1-codex-mini
      - auto           # Final fallback: let Cursor decide
    final_fallback: auto

  claude:
    chain:
      - opus           # Try opus first
      - sonnet         # Fall back to sonnet
      - haiku          # Final fallback
    final_fallback: haiku
```

**How it works:**

1. Agent runs with selected model (e.g., `opus`)
2. If quota exceeded, script detects error in stderr
3. Script retries with next model in chain (`sonnet`)
4. Process repeats until success or final fallback exhausted

---

## Validation Criteria

**File**: `~/.claude/config/validation_criteria.yml`

Defines two-tier validation system for security and quality checks.

### Tier 1: Critical (Blocking)

All Tier 1 checks must pass for approval.

```yaml
tier1:
  cross_verification:
    weight: 0.30
    description: "Multiple agents agree on key findings"
    threshold: 0.80
    enabled: true

  security:
    weight: 0.30
    description: "No security vulnerabilities introduced"
    checks:
      - id: no_hardcoded_secrets
        description: "No hardcoded secrets or credentials"
        severity: critical
      - id: input_validation
        description: "User input is validated and sanitized"
        severity: critical
      - id: no_sql_injection
        description: "Parameterized queries used for database access"
        severity: critical

  error_handling:
    weight: 0.20
    description: "Errors handled gracefully without information leakage"
    checks:
      - id: exceptions_caught
        description: "Exceptions properly caught and handled"
        severity: high

  breaking_changes:
    weight: 0.20
    description: "API and data compatibility maintained"
    checks:
      - id: api_compatibility
        description: "Public API signatures unchanged or versioned"
        severity: high
```

### Tier 2: Quality (Advisory)

Weighted score must be ≥ 0.60 for approval.

```yaml
tier2:
  bug_detection:
    weight: 0.25
    description: "No obvious bugs or logic errors"
    patterns:
      - id: null_reference
        description: "Potential null/undefined reference"
        regex: "\\.(\\w+)\\s*\\("

  performance:
    weight: 0.25
    description: "No performance anti-patterns"
    antipatterns:
      - id: quadratic_complexity
        description: "O(n^2) or worse complexity"
        indicators: ["nested loop", "forEach inside forEach"]

  maintainability:
    weight: 0.25
    description: "Code is readable and maintainable"
    thresholds:
      max_cyclomatic_complexity: 15
      max_function_length: 50
      max_file_length: 500

  test_coverage:
    weight: 0.25
    description: "Changes have corresponding tests"
    thresholds:
      minimum_coverage: 0.80
```

### Scoring

```yaml
scoring:
  tier1_pass_threshold: 1.0  # All tier1 checks must pass
  tier2_acceptable_threshold: 0.60

  verdicts:
    approved:
      tier1_passed: true
      tier2_min_score: 0.60
    needs_review:
      tier1_passed: true
      tier2_min_score: 0.0
    blocked:
      tier1_passed: false
```

**Verdict Examples:**

- Tier 1: 100% pass, Tier 2: 0.85 → **APPROVED**
- Tier 1: 100% pass, Tier 2: 0.45 → **NEEDS_REVIEW** (quality concerns)
- Tier 1: Security fail → **BLOCKED** (critical failure)

### Command-Specific Overrides

```yaml
command_overrides:
  refactor-python:
    tier1_required: true
    tier1_checks:
      - security
      - error_handling
      - breaking_changes
      - cross_verification
    tier2_required: true
    tier2_threshold: 0.80  # Higher threshold for refactoring
    consensus_threshold: 0.80

  docs-diagrams:
    tier1_required: false
    tier2_required: false
    # No validation for diagram generation
```

### Customizing Validation per Command

Validation behavior is customized through the `command_overrides` section of
`validation_criteria.yml` itself — this is the mechanism the validation engine
(`agents/validation.py`) actually loads.

**File**: `~/.claude/config/validation_criteria.yml`

#### Structure

```yaml
command_overrides:
  refactor-python:
    tier1_required: true
    tier1_checks:
      - security
      - error_handling
      - breaking_changes
      - cross_verification
    tier2_required: true
    tier2_threshold: 0.80
    consensus_threshold: 0.80
    consensus_action:
      high: auto_proceed          # >=80%: Use unified recommendation
      medium: show_disagreements  # 50-79%: Highlight to user
      low: block_and_escalate     # <50%: Human review required

  docs-readme:
    tier1_required: false
    tier2_required: true
    tier2_checks:
      - maintainability
    parallel_agents: false
```

When `parallel_agent.py --validate` runs with a `--command` context, the
matching override replaces the default tier requirements for that run; the
result reports `command_overrides_applied: true`.

#### How Overrides Work

1. **Base criteria loaded**: `~/.claude/config/validation_criteria.yml`
   (tier1/tier2 definitions and verdict thresholds)
2. **Command override selected**: the entry under `command_overrides:`
   matching the invoked command, if any
3. **Verdict computed**: APPROVED / NEEDS_REVIEW / BLOCKED per the
   (possibly overridden) tier requirements

> **Note**: A standalone `validation_overrides.yml` file with
> pattern-based project checks (as shipped in
> `docs/templates/validation-overrides/`) is a design sketch — no code
> loads that file today. Use `command_overrides` above for working
> customization; the templates document the checks worth adopting if the
> loader is implemented (tracked in issue #325).

---

## Model Selection

### Model Tiers

#### Cursor Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gpt-5.1-codex-mini | Quick queries | Lowest |
| `flash` | gpt-5.1-codex | Code review (default) | Medium |
| `advanced` | gpt-5.2 | Security analysis | Highest |
| `auto` | (Cursor decides) | Let Cursor optimize | Variable |

#### Claude Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `haiku` | claude-haiku-4-5-20251001 | Quick queries | Lowest |
| `sonnet` | claude-sonnet-4-6 | Code review (default) | Medium |
| `opus` | claude-opus-4-8 | Security analysis | Higher |
| `fable` | claude-fable-5 | Security tasks (default) | Highest |

#### Gemini Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `flash` | gemini-3-flash-preview | General use (default) | Lower |
| `pro` | gemini-3-pro-preview | Complex analysis | Higher |

#### Codex Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gpt-5.4-mini | Quick queries | Lowest |
| `flash` | gpt-5.4 | Code review (default) | Medium |
| `advanced` | gpt-5.5 | Security analysis | Highest |

#### Antigravity Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | Gemini 3.5 Flash (Low) | Quick queries | Lowest |
| `flash` | Gemini 3.5 Flash (High) | General use (default) | Medium |
| `advanced` | Claude Opus 4.6 (Thinking) | Complex analysis | Highest |

**Note**: Antigravity's catalog is managed by the `agy` CLI and may lag the direct
API (e.g. Opus 4.6 vs 4.8). Run `agy models` to see the live model list, which is
validated by `model_check.sh`.

### Selecting Models

**Via CLI flags:**

```bash
# Use advanced models for security-critical code
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --review auth.py

# Use lightweight models for quick questions
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  "What is this function doing?"
```

**Via environment variables:**

```bash
export CURSOR_MODEL_ADVANCED="gpt-5.2"
export CURSOR_MODEL_FLASH="gpt-5.1-codex"
export CURSOR_MODEL_MINI="gpt-5.1-codex-mini"

~/.claude/scripts/parallel_agent.py --cursor-model advanced "Task"
```

**Via command_config.yml** (see task_model_defaults above)

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

## CLI Agent Command Configuration

**File**: `configs/claude/config/parallel_agent.yml` — `cli_agents:` block

Defines how `parallel_agent.py` invokes each CLI provider. Adding a CLI provider
is configuration-only — define its command shape here plus `model_tiers`,
`rate_limits`, and `credit_fallback` entries in the same file.

```yaml
cli_agents:
  # claude/gemini entries back the OAuth CLI fallback: used when the provider
  # SDK or its API key is unavailable but the CLI is installed and logged in.
  claude:
    binary: claude
    base_args: []
    model_args: ["--model", "{model}"]
    prompt_args: ["-p", "{prompt}"]
    output: stdout
  gemini:
    binary: gemini
    base_args: []
    model_args: ["-m", "{model}"]
    prompt_args: ["-p", "{prompt}"]
    output: stdout
  cursor:
    binary: cursor
    base_args: []
    model_args: ["--model", "{model}"]
    output: stdout
  codex:
    binary: codex
    base_args: ["exec", "--full-auto", "--color", "never",
                "--output-last-message", "{output_file}"]
    model_args: ["--model", "{model}"]
    output: file_then_stdout
  antigravity:
    binary: agy
    base_args: []
    model_args: ["--model", "{model}"]
    prompt_args: ["--print", "{prompt}"]
    output: stdout
```

`output: file_then_stdout` reads the tempfile first, falling back to stdout;
`output: stdout` streams directly. `{model}`, `{prompt}`, and `{output_file}` are
substitution tokens filled at runtime.

### Execution Backend (SDK vs CLI Fallback)

Claude and Gemini pick an execution backend per run (`agents/cli.py`
`select_backend()`):

1. **SDK** — when the provider package (`anthropic` / `google-genai`) AND its API
   key (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present.
2. **CLI fallback** — otherwise, when the provider CLI (`claude` / `gemini`) is on
   PATH. OAuth/subscription logins work here with no API key — this is the default
   path on machines authenticated via `claude` / Gemini OAuth login.
3. **SDK with its own auth** (ADC/OAuth) as a last resort, else the provider is
   skipped with a warning.

The CLI fallback uses the `cli_agents.claude` / `cli_agents.gemini` command shapes
above. Cursor, Codex, and Antigravity always run via their CLI entries.

---

## Command-Line Options

### Agent Selection

```bash
--cursor-only          # Run only Cursor Agent
--gemini-only          # Run only Gemini CLI
--claude-only          # Run only Claude CLI
--codex-only           # Run only Codex CLI
--antigravity-only     # Run only Antigravity (agy)
--no-claude            # Disable Claude CLI
--no-cursor            # Disable Cursor Agent
--no-gemini            # Disable Gemini CLI
--no-codex             # Disable Codex CLI
--no-antigravity       # Disable Antigravity for this run
```

### Model Selection

```bash
--cursor-model <tier>       # Cursor model: mini, flash, advanced, auto (default: flash)
--claude-model <tier>       # Claude model: haiku, sonnet, opus, fable (default: sonnet)
--gemini-model <tier>       # Gemini model: flash, pro (default: flash)
--codex-model <tier>        # Codex model: mini, flash, advanced, auto (default: auto)
--antigravity-model <tier>  # Antigravity model: mini, flash, advanced (default: flash)
```

### Execution Modes

```bash
--analyze <file>       # Analyze a specific file for bugs/security
--review <file>        # Code review a file
--improve <file>       # Improve an observation YAML
```

### Output Options

```bash
--json                 # Output results in JSON format
--full-output          # Include complete agent outputs (no truncation)
--validate             # Check outputs against success criteria
--output <dir>         # Custom output directory (default: ~/.claude/.agent_outputs)
```

### Runtime Options

```bash
--timeout <seconds>    # Timeout per agent (default: 600)
--check-credits        # Run pre-flight credit check before execution
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

## Examples

### Example 1: Lightweight Security Scan

```bash
~/.claude/scripts/parallel_agent.py \
  --cursor-model mini \
  --claude-model haiku \
  --timeout 120 \
  --review auth.py
```

**Effect:**

- Uses cheapest models (mini/haiku)
- 2-minute timeout
- Still runs Tier 1 security validation

### Example 2: Deep Security Analysis

```bash
~/.claude/scripts/parallel_agent.py \
  --cursor-model advanced \
  --claude-model opus \
  --gemini-model pro \
  --timeout 900 \
  --full-output \
  --validate \
  --review auth.py
```

**Effect:**

- Uses most powerful models
- 15-minute timeout
- Full output (no truncation)
- Explicit validation checks

### Example 3: Single Agent with Custom Output

```bash
~/.claude/scripts/parallel_agent.py \
  --claude-only \
  --claude-model sonnet \
  --json \
  --output /tmp/analysis \
  "Analyze this codebase"
```

**Effect:**

- Only Claude runs (no Cursor/Gemini)
- JSON output format
- Custom output directory

---

## Related Documents

- [Getting Started](GETTING_STARTED.md) - Installation and basic usage
- [Troubleshooting](TROUBLESHOOTING.md) - Common configuration issues
- [Architecture Diagrams](ARCHITECTURE_DIAGRAMS.md) - Configuration hierarchy diagram
- [CLAUDE.md](../CLAUDE.md) - Repository context
