# Configuration Guide

> Comprehensive reference for all Manifest configuration options

**Last Updated**: 2026-06-08
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
8. [Command-Line Options](#command-line-options)
9. [Override Precedence](#override-precedence)

---

## Configuration Files

All configuration files are located in `~/.claude/config/`:

| File | Purpose | Format |
|------|---------|--------|
| `services.yml` | Agent enable/disable states | YAML |
| `command_config.yml` | Tool policies, thresholds, model defaults | YAML |
| `validation_criteria.yml` | Tier 1/2 security and quality rules | YAML |
| `skillclaw.yml` | SkillClaw proxy, storage, capture, evolve, and promotion settings | YAML |

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
      - mini     # Lightweight (o4-mini)
      - flash    # Balanced (o3, default)
      - advanced # Maximum capability (o3-pro)
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

SkillClaw is an **opt-in** local proxy that captures agent interactions, evolves skills with a
local LLM, and opens review PRs. It is **disabled by default** and does not affect any agent
behavior unless explicitly enabled.

### Enabling and Disabling

```bash
# Enable SkillClaw (installs daemon + shell wrappers)
./bootstrap.sh --enable-skillclaw

# Disable SkillClaw (removes wrappers, stops daemon)
./bootstrap.sh --disable-skillclaw

# Reconfigure alongside other toggles
./bootstrap.sh --reconfigure --enable-skillclaw --disable-cursor
```

When enabled, `services.yml` gains a `skillclaw:` stanza set to `enabled: true`.

### What skillclaw.yml Configures

```yaml
# Proxy — local HTTP interception layer
proxy:
  host: 127.0.0.1
  port: 8765            # All capture traffic passes through this port

# Storage — session and evolved-skill data (chmod 700; secrets scrubbed before evolution)
storage:
  root: ~/.skillclaw    # Top-level store; created with mode 700
  sessions: ~/.skillclaw/sessions
  evolved: ~/.skillclaw/evolved

# Capture — which agents are wired through the proxy
# (gemini and cursor-agent are documented follow-ups; not yet wired)
capture:
  agents:
    claude:
      env: ANTHROPIC_BASE_URL   # Set to http://127.0.0.1:8765 when proxy is up
    codex:
      env: OPENAI_BASE_URL      # Set to http://127.0.0.1:8765/v1 when proxy is up
      path: /v1

# Evolution — how captured sessions are improved into new skill candidates
evolve:
  mode: workflow
  provider:
    primary:
      base_url: http://127.0.0.1:11434/v1   # Local Ollama (preferred; no cloud cost)
      model: qwen2.5-coder
    fallback:
      provider: anthropic
      model: claude-haiku-4-5-20251001      # Cloud fallback when Ollama is unavailable

# Promotion — how evolved skills become PRs
promotion:
  branch_prefix: skillclaw/evolve-
  pr_base: main
  pr_labels:
    - needs-review
    - follow-up
```

### Fail-Open Capture

Shell wrapper functions replace the `claude` and `codex` commands. Before routing a call
through the proxy, the wrapper probes the daemon's health endpoint:

```bash
curl -sf --max-time 0.3 http://127.0.0.1:8765/health
```

If the probe fails (daemon down, slow to start, etc.) the wrapper falls back to the real CLI
binary directly — **agents are never blocked by a dead daemon**.

To bypass capture for a single shell session without disabling SkillClaw globally:

```bash
export SKILLCLAW_BYPASS=1
```

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

### Project-Specific Validation Overrides

Create project-specific validation rules by adding a `validation_overrides.yml` file to your
project's `configs/claude/config/` directory.
This extends the base validation criteria with domain-specific checks.

**File**: `configs/claude/config/validation_overrides.yml` (in your project)

#### Structure

```yaml
# Project-Specific Validation Overrides
# Extends ~/.claude/config/validation_criteria.yml

project_tier1:
  # Custom Tier 1 checks for your project
  custom_security_check:
    weight: 0.30
    severity: critical
    description: "Project-specific security requirement"
    applies_to:
      - "path/to/**/*.py"
      - "another/path/**/*.js"
    checks:
      - id: check_identifier
        description: "What this check validates"
        patterns:
          - "regex pattern to match good code"
        patterns_bad:
          - "regex pattern to match bad code"

project_tier2:
  # Custom Tier 2 checks for your project
  custom_quality_check:
    weight: 0.25
    severity: medium
    description: "Project-specific quality requirement"
    applies_to:
      - "**/*.ts"
    checks:
      - id: check_identifier
        description: "What this check validates"
        indicators:
          - "pattern1"
          - "pattern2"

# Exemptions for specific paths
exemptions:
  - path: "**/tests/**/*.py"
    reason: "Test files"
    skip_checks:
      - custom_security_check

  - path: "**/migrations/*.py"
    reason: "Generated migration files"
    skip_checks:
      - custom_quality_check
```

#### Framework-Specific Examples

**Django Projects**: See `templates/validation-overrides/django-security.yml`

- CSRF protection checks
- SQL injection prevention (no raw SQL with string interpolation)
- XSS protection (template auto-escaping)
- SECRET_KEY from environment
- Migration safety (reversibility, backwards compatibility)

**Express.js/Node.js Projects**: See `templates/validation-overrides/express-security.yml`

- Input validation (Joi, Zod schemas)
- SQL injection prevention (parameterized queries)
- Authentication middleware
- Helmet.js security headers
- Rate limiting on sensitive endpoints

**Go Projects**: See `templates/validation-overrides/go-security.yml` (coming soon)

- SQL injection (database/sql parameterized queries)
- Path traversal prevention
- Secrets in environment variables (not code)
- Context usage in HTTP handlers

#### How Overrides Work

1. **Base criteria loaded first**: `~/.claude/config/validation_criteria.yml`
2. **Project overrides merged**: `configs/claude/config/validation_overrides.yml`
3. **Project checks added**: New `project_tier1` and `project_tier2` sections
4. **Exemptions applied**: Specific paths can skip certain checks

**Example workflow**:

```bash
# 1. Copy template for your framework
cp templates/validation-overrides/django-security.yml \
   configs/claude/config/validation_overrides.yml

# 2. Customize for your project
vim configs/claude/config/validation_overrides.yml

# 3. Test validation
~/.claude/scripts/parallel_agent.py --validate --review path/to/file.py

# 4. Adjust thresholds or exemptions as needed
```

#### Pattern Syntax

**Simple pattern matching**:

```yaml
patterns:
  - "jwt.verify"           # Must contain this string
  - "authenticate"         # Or this string
```

**Regex patterns**:

```yaml
patterns:
  - "\\$\\{.*\\}.*SELECT"  # Template literal in SQL (bad)
  - "req\\.body\\["        # Direct req.body access (bad)
```

**Context-aware patterns**:

```yaml
patterns:
  - "current_version"      # Must contain this...
context: "UpdateTransaction"  # ...within this context
```

**Good vs Bad patterns**:

```yaml
patterns_good:
  - "cursor.execute.*%s"   # Parameterized query (good)
patterns_bad:
  - "cursor.execute.*f\""  # f-string in SQL (bad)
```

#### Validation Output

When project-specific checks are used:

```text
🔍 Validation Results (with project overrides)

Base Checks:
  ✅ Cross-verification: PASS
  ✅ Security (base): PASS
  ✅ Error handling: PASS

Project-Specific Checks:
  ✅ Django CSRF: PASS
     - CSRF middleware enabled in settings.py
  ⚠️  Django SQL injection: WARNING
     - raw() call found in queries.py:42
     - Recommendation: Use parameterized queries
  ❌ Django template safety: FAIL
     - 'safe' filter used without justification (templates/user.html:15)

Overall: NEEDS_REVIEW (tier1 pass, tier2: 0.55)
```

#### Best Practices

1. **Start with a template**: Use framework examples from `templates/validation-overrides/`
2. **Document your checks**: Clear descriptions help team understand violations
3. **Use exemptions wisely**: Tests and generated files often need exemptions
4. **Test incrementally**: Add one check at a time, verify it works
5. **Version control**: Commit `validation_overrides.yml` to your repository
6. **Team alignment**: Discuss thresholds and exemptions with your team

#### Troubleshooting

**Check not triggering**:

- Verify `applies_to` paths match your file structure
- Test regex patterns with a simple script
- Enable verbose logging (if available)

**Too many false positives**:

- Refine `patterns` to be more specific
- Add `context` to narrow scope
- Use `exemptions` for known good cases

**Check too strict**:

- Lower `weight` for tier2 checks
- Add exceptions for edge cases
- Document reasoning in comments

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
| `haiku` | haiku | Quick queries | Lowest |
| `sonnet` | sonnet | Code review (default) | Medium |
| `opus` | opus | Security analysis | Highest |

#### Gemini Models

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `flash` | gemini-3-flash-preview | General use (default) | Lower |
| `pro` | gemini-3-pro-preview | Complex analysis | Higher |

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

### Feature Flags

```bash
# Enable pre-flight credit check before running agents
export CHECK_CREDITS_PREFLIGHT="true"
```

---

## Command-Line Options

### Agent Selection

```bash
--cursor-only          # Run only Cursor Agent
--gemini-only          # Run only Gemini CLI
--claude-only          # Run only Claude CLI
--codex-only           # Run only Codex CLI
--no-claude            # Disable Claude CLI
--no-cursor            # Disable Cursor Agent
--no-gemini            # Disable Gemini CLI
--no-codex             # Disable Codex CLI
```

### Model Selection

```bash
--cursor-model <tier>  # Cursor model: mini, flash, advanced, auto (default: flash)
--claude-model <tier>  # Claude model: haiku, sonnet, opus (default: sonnet)
--gemini-model <tier>  # Gemini model: flash, pro (default: flash)
--codex-model <tier>   # Codex model: mini, flash, advanced, auto (default: auto)
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
