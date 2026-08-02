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

  # Cursor Agent - headless CLI for code analysis
  cursor:
    enabled: true
    command: cursor-agent
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
      - mini     # Lightweight (gpt-5.6-luna)
      - flash    # Balanced (gpt-5.6-terra, default)
      - advanced # Maximum capability (gpt-5.6-sol)
      - auto     # Use Codex config default model

  # Graphify - knowledge-graph generator (managed tool, not an orchestration agent)
  graphify:
    enabled: true            # default-enabled; --disable-graphify to opt out
    command: graphify
    description: "Knowledge-graph generator (/graphify); host-agent backend, no key required"

  # pilotfish - cost-tiered role-agents (~/.claude/agents/) + delegation policy reference.
  # Opt-in, config-only, Claude-only. Enabling deploys six role-agents (scout, Explore,
  # mech-executor, executor, verifier, security-executor) that bind to Claude Code's built-in
  # model aliases (haiku/sonnet/opus) plus a read-on-demand delegation policy; disabling removes
  # exactly those. Does not change the main-session model. Toggle: --enable-pilotfish.
  pilotfish:
    enabled: false           # opt-in; --enable-pilotfish to turn on
    description: "Cost-tiered role-agents + delegation policy, verifier-gated (opt-in, Claude-only)"

  # devpanel - critic-gated dev/debug/test role-agents (~/.claude/agents/) + delegation policy
  # reference. Opt-in, config-only, Claude-only, independent of pilotfish (own toggle/marker,
  # same target dir, disjoint filenames — both may be enabled together). Enabling deploys five
  # role-agents (developer, debugger, tester + shared validators spec-guard, chaos-engineer) in
  # a propose->critique->refactor loop; disabling removes exactly those. Toggle: --enable-devpanel.
  devpanel:
    enabled: false           # opt-in; --enable-devpanel to turn on
    description: "developer/debugger/tester + spec-guard/chaos-engineer critic loop (opt-in, Claude-only)"

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

# Enable browser-use (Python E2E browser automation for smoke-manage UI steps)
./bootstrap.sh --reconfigure --enable-browser-use

# Disable Graphify (managed knowledge-graph tool; default-enabled)
./bootstrap.sh --reconfigure --disable-graphify
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
  docs_improve_lines: 500         # Trigger parallel agents when total doc lines > 500
  docs_diagrams_modules: 5        # Trigger when analyzing 5+ unique imports/modules

  # Code quality skill auto-triggers
  skill_file_lines: 500           # File > 500 lines
  skill_function_count: 10        # > 10 functions per file
  skill_class_count: 5            # > 5 classes per file
  skill_cyclomatic_complexity: 15 # Cyclomatic complexity > 15
```

### Consensus Thresholds

```yaml
# Consensus thresholds for parallel agent decisions (float 0.0-1.0)
consensus:
  high: 0.80    # >=0.80: Auto-proceed with unified recommendation
  medium: 0.50  # 0.50-0.79: Highlight disagreements to user
  low: 0.0      # <0.50: Block and escalate for human review
```

**Example**: If 2 of 3 agents agree → 67% consensus → medium confidence → disagreements highlighted

### Tool Policies

Defines which tools each command can use:

```yaml
tool_policies:
  python-refactor:
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

  docs-generate-diagrams:
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
  python-refactor:
    tier1_required: true
    tier1_checks:
      - security
      - error_handling
      - breaking_changes
      - cross_verification
    tier2_required: true
    tier2_threshold: 0.80  # Higher threshold for refactoring
    consensus_threshold: 0.80

  docs-generate-diagrams:
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
  python-refactor:
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

  docs-improve-readme:
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

Every pin below carries its verification status as of **2026-07-29**. VERIFIED
means a real one-shot call through that provider's own CLI answered; UNVERIFIED
means the pin is retained so tier lookups resolve, but nothing has confirmed it.
The distinction is load-bearing — pins transcribed from documentation are what
produced this repo's 404ing Gemini tiers. Re-check with `model_check.sh`
(`MODEL_CHECK_PROBE=1` on machines with no API key).

#### Cursor Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | cursor-grok-4.5-low | Quick queries | Lowest |
| `flash` | cursor-grok-4.5-medium | Code review (default) | Medium |
| `advanced` | cursor-grok-4.5-high | Security analysis | Highest |
| `auto` | (Cursor decides) | Let Cursor optimize | Variable |

One effort ladder from a single family, so the tiers genuinely differ — all three
previously read `auto`, which made the tier abstraction inert. `auto` and
`composer-2.5` also verified and remain valid alternates. Cursor's newer premium
ladder (`claude-opus-5-thinking-*`, `claude-fable-5-thinking-*`, `gpt-5.6-sol-*`,
`kimi-k3-high`) is **not** pinned: every one returned an account usage-limit
`ActionRequiredError` (resets **2026-08-12**), making them unverifiable rather
than broken. Re-probe after that date and promote `advanced` if they answer.

#### Claude Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `haiku` | claude-haiku-4-5 | Quick queries | Lowest |
| `sonnet` | claude-sonnet-5 | Code review (default) | Medium |
| `opus` | claude-opus-5 | Security analysis | Higher |
| `fable` | claude-fable-5 | Security tasks (default) | Highest |

Full IDs, not the `opus`/`sonnet`/`haiku`/`fable` aliases (which also work): an
alias is a moving target the provider can remap, so pinning one would let a tier
change model without a diff in this repo.

#### Gemini Models — UNVERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `flash` | gemini-3-flash-preview | General use (default) | Lower |
| `pro` | gemini-3-pro-preview | Complex analysis | Higher |

**The `gemini` CLI is non-functional on a free-tier account.** Every invocation
fails at the eligibility layer — before model selection — with
`IneligibleTierError`: *"no longer supported for Gemini Code Assist for
individuals … migrate to the Antigravity suite"*. With no `GOOGLE_API_KEY` /
`GEMINI_API_KEY` set, the REST models endpoint cannot confirm these IDs either,
so both pins are unproven. Google's own stated remedy is the Antigravity table
below, which serves Gemini models and *is* verified.

#### Codex Models — VERIFIED (2026-08-02)

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gpt-5.6-luna | Quick queries | Lowest |
| `flash` | gpt-5.6-terra | Code review (default) | Medium |
| `advanced` | gpt-5.6-sol | Security analysis | Highest |

VERIFIED 2026-08-02: all three pins answered a live
`codex exec --skip-git-repo-check --model <id>` probe on a ChatGPT login.
The CLI still exposes no model-listing command (no `models`, `models list`,
`--list-models`), so `model_check.sh` has no listing source — re-verify with
`MODEL_CHECK_PROBE=1 model_check.sh`. gpt-5.4* retire from ChatGPT-login
Codex on 2026-08-31.

#### Antigravity Models — VERIFIED

| Tier | Model Name | Use Case | Cost |
|------|------------|----------|------|
| `mini` | gemini-3.6-flash-low | Quick queries | Lowest |
| `flash` | gemini-3.6-flash-high | General use (default) | Medium |
| `advanced` | claude-opus-4-6-thinking | Complex analysis | Highest |

**Note**: these are slugs, not display labels. `agy models` emitted labels like
`Gemini 3.5 Flash (Low)` under agy 1.1.1 and emits slugs under 1.1.8. agy still
*accepts* the old labels, so the previous pins were never broken at runtime —
they had merely stopped matching the catalog, which made `model_check.sh` score
them STALE for a cosmetic reason. `mini`/`flash` keep the prior low/high effort
split, moved up to the 3.6 flash family now that it exists. Antigravity's
catalog is managed by the `agy` CLI and may lag the direct API (its top Claude
entry is Opus 4.6, where the Claude table above is on Opus 5). Run `agy models`
for the live list, which `model_check.sh` validates.

#### Devin Models

Devin has **no tier table on purpose**. `devin models list` is login-gated, so the
account's real catalog cannot be enumerated from this repo, and pinning names read
off a docs page is how a stale pin turns into a runtime 404. Consequences:

- `--devin-model` defaults to `auto`, which sends no `--model` flag at all and lets
  the account default stand.
- Any other value is passed through verbatim, so you can name a real model
  (`--devin-model opus`) once `devin models list` shows you what your account has.
- `credit_fallback.devin` is empty: there is no known cheaper tier to fall back to.

**Skills, rules, and MCP servers are inherited, not copied.** `devin` reads
`~/.claude/skills` and `~/.claude/CLAUDE.md` directly when
`~/.config/devin/config.json` sets `read_config_from.claude: true` (bootstrap pins
it). Copying the skills into `~/.config/devin/skills` would register each one twice
— `/devin:<name>` beside `/claude:<name>` — so `agent_roster.yml` marks devin
`skills_sync: false`. MCP servers arrive the same way: `devin mcp list` showed 11
servers on a Manifest-configured home and 3 with `read_config_from.cursor: false`,
the missing 8 being exactly what `--install-mcp` wrote to `~/.cursor/mcp.json`.
Verify the whole inheritance chain with:

```bash
devin skills list | grep -c '~/.claude/skills'   # expect your skill count
devin rules list                                 # expect a CLAUDE entry
devin mcp list                                   # expect your registry
```

**Known interaction:** `devin rules list` reports a YAML parse error for each
generated Cursor rule (`~/.cursor/rules/*.mdc`), because `generate_cursor_rules.sh`
emits `globs:` as a string and Devin's parser requires a sequence. Those rules are
per-skill duplicates of skills Devin already loads from `~/.claude/skills`, so the
errors are noise, not lost capability; the fix (emit a YAML list) is deferred
because Cursor's own tolerance for the list form is unverified.

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
    binary: cursor-agent
    base_args: ["--print", "--output-format", "text", "--mode", "ask"]
    model_args: ["--model", "{model}"]
    prompt_args: ["{prompt}"]
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
substituted at runtime.

### Synthesis configuration

**File**: `configs/claude/config/parallel_agent.yml` — `synthesis:` block

When consensus falls below `threshold` (default 0.50), `SynthesisEngine` merges
agent outputs using the `synthesis.md` prompt template.

```yaml
synthesis:
  enabled: true
  threshold: 0.50
  model: "sonnet"       # model_tiers.claude tier
  timeout: 300
  backend: auto         # auto | cli | sdk
```

| `backend` | Behavior |
|-----------|----------|
| `auto` (default) | Same as primary claude agent: SDK when package + `ANTHROPIC_API_KEY`, else `claude -p` CLI |
| `cli` | Always invoke `claude -p` (OAuth/subscription login) |
| `sdk` | Always use Anthropic SDK (requires `ANTHROPIC_API_KEY`; for headless/CI) |

### Execution Backend (SDK vs CLI Fallback)

Claude and Gemini pick an execution backend per run (`agents/config.py`
`select_backend()`):

1. **SDK** — when the provider package (`anthropic` / `google-genai`) AND its API
   key (`ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) are both present.
2. **CLI fallback** — otherwise, when the provider CLI (`claude` / `gemini`) is on
   PATH. OAuth/subscription logins work here with no API key — this is the default
   path on machines authenticated via `claude` / Gemini OAuth login.
3. **SDK with its own auth** (ADC/OAuth) as a last resort, else the provider is
   skipped with a warning.

The CLI fallback uses the `cli_agents.claude` / `cli_agents.gemini` command shapes
above. Cursor, Codex, Antigravity, and Devin always run via their CLI entries.

---

## Command-Line Options

### Agent Selection

```bash
--cursor-only          # Run only Cursor Agent
--gemini-only          # Run only Gemini CLI
--claude-only          # Run only Claude CLI
--codex-only           # Run only Codex CLI
--antigravity-only     # Run only Antigravity (agy)
--devin-only           # Run only Devin (opt-in; see below)
--no-claude            # Disable Claude CLI
--no-cursor            # Disable Cursor Agent
--no-gemini            # Disable Gemini CLI
--no-codex             # Disable Codex CLI
--no-antigravity       # Disable Antigravity for this run
--no-devin             # Disable Devin for this run
```

Devin ships **disabled** (`agent_roster.yml: devin.enabled_default: false`). Enable
it with `./bootstrap.sh --enable-devin` after `devin auth login` — an
unauthenticated agent errors instead of abstaining, which drags the consensus
metric into a verdict that is not a finding.

### Model Selection

```bash
--cursor-model <tier>       # Cursor model: mini, flash, advanced, auto (default: flash)
--claude-model <tier>       # Claude model: haiku, sonnet, opus, fable (default: sonnet)
--gemini-model <tier>       # Gemini model: flash, pro (default: flash)
--codex-model <tier>        # Codex model: mini, flash, advanced, auto (default: auto)
--antigravity-model <tier>  # Antigravity model: mini, flash, advanced (default: flash)
--devin-model <name>        # Devin model: passed through verbatim (default: auto = no pin)
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
