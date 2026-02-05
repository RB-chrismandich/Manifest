# Architecture Diagrams

> Visual documentation of the Manifest parallel LLM agent orchestration framework

**Last Updated**: 2026-02-05
**Project**: Manifest - AI Agent Orchestration Framework

---

## Table of Contents

1. [Application Architecture](#application-architecture)
2. [Bootstrap Installation Flow](#bootstrap-installation-flow)
3. [Parallel Agent Execution Flow](#parallel-agent-execution-flow)
4. [Command Processing Architecture](#command-processing-architecture)
5. [Validation Pipeline](#validation-pipeline)
6. [Model Selection & Credit Fallback](#model-selection--credit-fallback)
7. [Configuration Layer](#configuration-layer)
8. [Cross-Verification Consensus](#cross-verification-consensus)
9. [Service State Management](#service-state-management)

---

## Application Architecture

High-level overview of the complete system showing major components and their relationships.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef output fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef external fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User"]:::input
    BOOTSTRAP["bootstrap.sh"]:::process
    CLAUDE_CLI["Claude CLI"]:::process

    subgraph "Installation & Setup"
        BOOTSTRAP
        INSTALL["Dependency Installation"]:::process
        DEPLOY["Config Deployment"]:::process
        AUTH["Authentication Setup"]:::process
        BOOTSTRAP --> INSTALL --> DEPLOY --> AUTH
    end

    subgraph "Configuration Layer"
        SERVICES["services.yml"]:::config
        COMMAND_CFG["command_config.yml"]:::config
        VALIDATION["validation_criteria.yml"]:::config
    end

    subgraph "Command Execution"
        SKILL["Auto-triggered Skills"]:::process
        COMMANDS["User Commands<br/>(/refactor, /improve-docs, etc.)"]:::process
        ORCHESTRATOR["parallel_agent.sh<br/>Orchestrator"]:::process
    end

    subgraph "Agent Execution Layer"
        CURSOR["Cursor Agent"]:::external
        GEMINI["Gemini CLI"]:::external
        CLAUDE_AGENT["Claude CLI Agent"]:::external
    end

    subgraph "Analysis & Output"
        MONITOR["Agent Monitor"]:::process
        VALIDATE_OUT["Output Validation"]:::process
        CROSS_VERIFY["Cross-Verification"]:::process
        SYNTHESIS["Consensus Scoring"]:::process
        SUMMARY["Summary Generation"]:::output
    end

    USER --> BOOTSTRAP
    USER --> CLAUDE_CLI
    CLAUDE_CLI --> SKILL
    CLAUDE_CLI --> COMMANDS

    SERVICES --> ORCHESTRATOR
    COMMAND_CFG --> ORCHESTRATOR
    VALIDATION --> ORCHESTRATOR

    COMMANDS --> ORCHESTRATOR
    SKILL --> ORCHESTRATOR

    ORCHESTRATOR --> CURSOR
    ORCHESTRATOR --> GEMINI
    ORCHESTRATOR --> CLAUDE_AGENT

    CURSOR --> MONITOR
    GEMINI --> MONITOR
    CLAUDE_AGENT --> MONITOR

    MONITOR --> VALIDATE_OUT
    VALIDATE_OUT --> CROSS_VERIFY
    CROSS_VERIFY --> SYNTHESIS
    SYNTHESIS --> SUMMARY

    SUMMARY --> USER
```

**Key Components:**

- **Bootstrap Layer**: Automated installation and configuration for macOS/Linux
- **Configuration Layer**: YAML-based configuration for services, commands, and validation
- **Command Execution**: User-invoked commands and auto-triggered skills
- **Agent Layer**: Three independent AI agents (Cursor, Gemini, Claude) running in parallel
- **Analysis Layer**: Output validation, cross-verification, and consensus scoring

---

## Bootstrap Installation Flow

Detailed bootstrap process showing platform detection, dependency installation, and service configuration.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef active fill:#22c55e,stroke:#166534,color:#fff
    classDef pending fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff
    classDef external fill:#3b82f6,stroke:#1d4ed8,color:#fff

    START["Start bootstrap.sh"]:::active
    DETECT["Detect Platform<br/>(macOS/Linux)"]:::pending

    PARSE["Parse Arguments<br/>(--enable/--disable services)"]:::pending
    LOAD_CFG["Load Existing<br/>services.yml"]:::pending

    CHECK_PKG["Check Package Manager<br/>(brew/apt/dnf/pacman)"]:::pending
    INSTALL_PKG["Install Package Manager<br/>(macOS: Homebrew)"]:::pending

    INSTALL_NODE["Install Node.js"]:::pending

    subgraph "CLI Installation"
        INSTALL_CLAUDE["Install Claude CLI<br/>(npm -g @anthropic-ai/claude-code)"]:::pending
        INSTALL_GEMINI["Install Gemini CLI<br/>(npm -g @google/gemini-cli)"]:::pending
        CHECK_CURSOR["Check Cursor<br/>(Open download page)"]:::pending
    end

    DEPLOY["Deploy .claude/ to ~/.claude/<br/>(backup if exists)"]:::active
    WRITE_SVC["Write services.yml<br/>(enabled services)"]:::active

    subgraph "Authentication"
        AUTH_CLAUDE["Claude: claude auth login"]:::external
        AUTH_GEMINI["Gemini: OAuth or API key"]:::external
        AUTH_CURSOR["Cursor: Sign in via IDE"]:::external
    end

    VERIFY["Verify Installation<br/>(check files & commands)"]:::active
    SUMMARY["Print Summary<br/>(service status, next steps)"]:::active
    DONE["Installation Complete"]:::active

    START --> DETECT
    DETECT --> PARSE
    PARSE --> LOAD_CFG
    LOAD_CFG --> CHECK_PKG

    CHECK_PKG -->|Missing| INSTALL_PKG
    CHECK_PKG -->|Found| INSTALL_NODE
    INSTALL_PKG --> INSTALL_NODE

    INSTALL_NODE --> INSTALL_CLAUDE
    INSTALL_NODE --> INSTALL_GEMINI
    INSTALL_NODE --> CHECK_CURSOR

    INSTALL_CLAUDE --> DEPLOY
    INSTALL_GEMINI --> DEPLOY
    CHECK_CURSOR --> DEPLOY

    DEPLOY --> WRITE_SVC
    WRITE_SVC --> AUTH_CLAUDE
    WRITE_SVC --> AUTH_GEMINI
    WRITE_SVC --> AUTH_CURSOR

    AUTH_CLAUDE --> VERIFY
    AUTH_GEMINI --> VERIFY
    AUTH_CURSOR --> VERIFY

    VERIFY --> SUMMARY
    SUMMARY --> DONE
```

**Platform Support:**

- **macOS**: Homebrew for package management
- **Linux**: apt, dnf, yum, pacman, zypper support
- **Services**: Toggle-based (--enable/--disable flags)
- **Reconfiguration**: Run with --reconfigure to update service settings

---

## Parallel Agent Execution Flow

End-to-end flow from command invocation through parallel agent execution to final output.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef output fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef validation fill:#fef2f2,stroke:#dc2626,color:#7f1d1d

    USER["User Invokes<br/>/refactor or script"]:::input

    PARSE["Parse Arguments<br/>(--review, --analyze, --cursor-model)"]:::process
    LOAD_SVC["Load services.yml<br/>(enabled services)"]:::process
    VALIDATE_AGENTS["Validate Agent<br/>Availability"]:::process

    BUILD["Build Prompts<br/>(per mode: review/analyze/improve)"]:::process

    RESOLVE["Resolve Model Tiers<br/>(mini/flash/advanced → gpt-5.2)"]:::process

    PREFLIGHT["Pre-flight Credit Check<br/>(optional)"]:::validation

    subgraph "Parallel Execution"
        CURSOR_EXEC["Cursor Agent<br/>cursor agent --model"]:::process
        GEMINI_EXEC["Gemini CLI<br/>gemini --model"]:::process
        CLAUDE_EXEC["Claude CLI<br/>claude --model"]:::process
    end

    MONITOR["Monitor Agents<br/>(PIDs, spinner UI)"]:::process

    VALIDATE_OUT["Validate Outputs<br/>(non-empty, no fatal errors)"]:::validation

    CROSS_VERIFY["Cross-Verification<br/>(consensus scoring)"]:::process

    JSON_OUT["JSON Output<br/>(results_YYYYMMDD_HHMMSS.json)"]:::output
    MD_OUT["Markdown Summary<br/>(summary_YYYYMMDD_HHMMSS.md)"]:::output

    USER --> PARSE
    PARSE --> LOAD_SVC
    LOAD_SVC --> VALIDATE_AGENTS
    VALIDATE_AGENTS --> BUILD
    BUILD --> RESOLVE
    RESOLVE --> PREFLIGHT

    PREFLIGHT --> CURSOR_EXEC
    PREFLIGHT --> GEMINI_EXEC
    PREFLIGHT --> CLAUDE_EXEC

    CURSOR_EXEC --> MONITOR
    GEMINI_EXEC --> MONITOR
    CLAUDE_EXEC --> MONITOR

    MONITOR --> VALIDATE_OUT
    VALIDATE_OUT --> CROSS_VERIFY

    CROSS_VERIFY --> JSON_OUT
    CROSS_VERIFY --> MD_OUT

    JSON_OUT --> USER
    MD_OUT --> USER
```

**Execution Characteristics:**

- **Parallel Execution**: All enabled agents run simultaneously (background processes)
- **Timeouts**: Default 600s (10 minutes) per agent, configurable via --timeout
- **Retry Logic**: Automatic retry on failure with exponential backoff
- **Progress Monitoring**: Real-time spinner UI showing agent status

---

## Command Processing Architecture

How user commands flow through the Claude Code CLI and trigger orchestration.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef user fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef skill fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef command fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef parallel fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User Input"]:::user

    subgraph "Claude Code CLI"
        DETECT["Detect Command Type"]:::decision
        SKILL_CHECK["Check Auto-Trigger<br/>Patterns"]:::decision
    end

    subgraph "Auto-Triggered Skills"
        CODE_QUAL["code-quality skill<br/>(security, complexity)"]:::skill
    end

    subgraph "User Commands"
        REFACTOR["/refactor<br/>(Python analysis)"]:::command
        SHELL_REF["/shell-refactor<br/>(Bash analysis)"]:::command
        GEN_DIAG["/generate-diagrams<br/>(Mermaid docs)"]:::command
        IMP_DOCS["/improve-docs<br/>(Diataxis framework)"]:::command
        IMP_README["/improve-readme<br/>(README structure)"]:::command
    end

    CHECK_THRESH["Check Thresholds<br/>(lines, modules, security patterns)"]:::decision

    PARALLEL_YES["Trigger Parallel Agents<br/>(parallel_agent.sh)"]:::parallel
    PARALLEL_NO["Single Agent Analysis<br/>(Claude only)"]:::command

    OUTPUT["Return Results<br/>to User"]:::user

    USER --> DETECT

    DETECT -->|Auto-trigger| SKILL_CHECK
    DETECT -->|User command| REFACTOR
    DETECT -->|User command| SHELL_REF
    DETECT -->|User command| GEN_DIAG
    DETECT -->|User command| IMP_DOCS
    DETECT -->|User command| IMP_README

    SKILL_CHECK -->|Match| CODE_QUAL

    CODE_QUAL --> CHECK_THRESH
    REFACTOR --> CHECK_THRESH
    SHELL_REF --> CHECK_THRESH
    GEN_DIAG --> CHECK_THRESH
    IMP_DOCS --> CHECK_THRESH
    IMP_README --> PARALLEL_NO

    CHECK_THRESH -->|Always| PARALLEL_YES
    CHECK_THRESH -->|Conditional| PARALLEL_YES
    CHECK_THRESH -->|Never| PARALLEL_NO

    PARALLEL_YES --> OUTPUT
    PARALLEL_NO --> OUTPUT
```

**Command Categories:**

| Command | Parallel Agents | Trigger Condition |
|---------|----------------|-------------------|
| `/refactor` | ALWAYS | N/A |
| `/shell-refactor` | ALWAYS | N/A |
| `code-quality` (skill) | ALWAYS | Auto-triggered |
| `/generate-diagrams` | CONDITIONAL | ≥5 unique imports |
| `/improve-docs` | CONDITIONAL | ≥500 lines |
| `/improve-readme` | NEVER | N/A |

---

## Validation Pipeline

Two-tier validation system for code review outputs.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef active fill:#22c55e,stroke:#166534,color:#fff
    classDef pending fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff

    START["Agent Outputs<br/>(Cursor, Gemini, Claude)"]:::pending

    subgraph "Tier 1: Critical Checks (Blocking)"
        T1_CROSS["Cross-Verification<br/>(consensus ≥80%)"]:::active
        T1_SEC["Security Issues<br/>(injection, XSS, secrets)"]:::active
        T1_ERR["Error Handling<br/>(no silent failures)"]:::active
        T1_BREAK["Breaking Changes<br/>(API compatibility)"]:::active
    end

    T1_PASS{"All Tier 1<br/>Pass?"}:::pending
    T1_BLOCK["BLOCKED<br/>(fix required)"]:::error

    subgraph "Tier 2: Quality Checks (Advisory)"
        T2_BUG["Bug Detection<br/>(null refs, off-by-one)"]:::pending
        T2_PERF["Performance<br/>(O(n²), memory leaks)"]:::pending
        T2_MAINT["Maintainability<br/>(complexity, naming)"]:::pending
        T2_TEST["Test Coverage<br/>(≥80% for new code)"]:::pending
    end

    T2_SCORE["Calculate Tier 2 Score<br/>(weighted average)"]:::pending
    T2_THRESH{"Score ≥ 0.60?"}:::pending

    APPROVED["APPROVED<br/>(proceed with changes)"]:::active
    NEEDS_REVIEW["NEEDS REVIEW<br/>(quality improvements suggested)"]:::pending

    START --> T1_CROSS
    START --> T1_SEC
    START --> T1_ERR
    START --> T1_BREAK

    T1_CROSS --> T1_PASS
    T1_SEC --> T1_PASS
    T1_ERR --> T1_PASS
    T1_BREAK --> T1_PASS

    T1_PASS -->|No| T1_BLOCK
    T1_PASS -->|Yes| T2_BUG

    T2_BUG --> T2_SCORE
    T2_PERF --> T2_SCORE
    T2_MAINT --> T2_SCORE
    T2_TEST --> T2_SCORE

    T2_SCORE --> T2_THRESH

    T2_THRESH -->|Yes| APPROVED
    T2_THRESH -->|No| NEEDS_REVIEW
```

**Tier 1 Criteria (Blocking):**

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Cross-Verification | 0.30 | Agents agree on key findings |
| Security | 0.30 | No injection, XSS, auth bypass, secrets |
| Error Handling | 0.20 | Proper exceptions, no silent failures |
| Breaking Changes | 0.20 | API compatibility, data migrations |

**Tier 2 Criteria (Quality):**

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Bug Detection | 0.25 | Logic errors, null refs, race conditions |
| Performance | 0.25 | No O(n²), memory leaks, blocking I/O |
| Maintainability | 0.25 | Clear naming, reasonable complexity |
| Test Coverage | 0.25 | ≥80% coverage for new code |

---

## Model Selection & Credit Fallback

Dynamic model selection based on task complexity with automatic fallback on credit exhaustion.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef task fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef model fill:#22c55e,stroke:#166534,color:#fff
    classDef fallback fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff

    subgraph "Task Types"
        SECURITY["Security<br/>(auth, crypto)"]:::task
        REVIEW["Code Review"]:::task
        ANALYZE["Bug Analysis"]:::task
        IMPROVE["Improvements"]:::task
        QUICK["Quick Query"]:::task
    end

    subgraph "Cursor Models"
        C_ADV["gpt-5.2<br/>(advanced)"]:::model
        C_FLASH["gpt-5.1-codex<br/>(flash)"]:::model
        C_MINI["gpt-5.1-codex-mini<br/>(mini)"]:::model
        C_AUTO["auto"]:::fallback
    end

    subgraph "Claude Models"
        CL_OPUS["opus"]:::model
        CL_SONNET["sonnet"]:::model
        CL_HAIKU["haiku"]:::model
    end

    subgraph "Gemini Models"
        G_PRO["gemini-3-pro-preview"]:::model
        G_FLASH["gemini-3-flash-preview"]:::model
    end

    CREDIT_ERR["Credit Exhaustion<br/>Detected"]:::error

    SECURITY --> C_ADV
    SECURITY --> CL_OPUS
    SECURITY --> G_PRO

    REVIEW --> C_FLASH
    REVIEW --> CL_SONNET
    REVIEW --> G_FLASH

    ANALYZE --> C_FLASH
    ANALYZE --> CL_SONNET
    ANALYZE --> G_FLASH

    IMPROVE --> C_MINI
    IMPROVE --> CL_HAIKU
    IMPROVE --> G_FLASH

    QUICK --> C_MINI
    QUICK --> CL_HAIKU
    QUICK --> G_FLASH

    C_ADV -->|Quota exceeded| CREDIT_ERR
    CL_OPUS -->|Quota exceeded| CREDIT_ERR

    CREDIT_ERR -->|Cursor fallback| C_FLASH
    C_FLASH -->|Quota exceeded| C_MINI
    C_MINI -->|Quota exceeded| C_AUTO

    CREDIT_ERR -->|Claude fallback| CL_SONNET
    CL_SONNET -->|Quota exceeded| CL_HAIKU
```

**Model Tier Mappings:**

| Tier | Cursor | Claude | Gemini |
|------|--------|--------|--------|
| Advanced/Opus/Pro | gpt-5.2 | opus | gemini-3-pro-preview |
| Flash/Sonnet | gpt-5.1-codex | sonnet | gemini-3-flash-preview |
| Mini/Haiku | gpt-5.1-codex-mini | haiku | N/A |
| Fallback | auto | haiku | N/A |

**Credit Detection:**

- Parse stderr for: `credit`, `quota`, `rate limit`, `exceeded`, `insufficient`
- Automatic fallback chain with exponential model downgrade
- Optional pre-flight check with `--check-credits` flag

---

## Configuration Layer

YAML-based configuration hierarchy showing how settings flow through the system.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef override fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef runtime fill:#f0fdf4,stroke:#16a34a,color:#14532d

    subgraph "Configuration Files (~/.claude/config/)"
        SERVICES["services.yml<br/>(enabled agents)"]:::config
        COMMAND_CFG["command_config.yml<br/>(thresholds, policies)"]:::config
        VALIDATION["validation_criteria.yml<br/>(tier 1/2 rules)"]:::config
    end

    subgraph "Command-Specific Overrides"
        REFACTOR_OVER["refactor:<br/>consensus ≥80%<br/>tier2 ≥0.80"]:::override
        SHELL_OVER["shell-refactor:<br/>consensus ≥75%<br/>tier2 ≥0.70"]:::override
        DOCS_OVER["improve-docs:<br/>tier1: false<br/>tier2: true"]:::override
    end

    subgraph "Runtime Parameters"
        CLI_ARGS["CLI Arguments<br/>(--cursor-model, --timeout)"]:::runtime
        ENV_VARS["Environment Variables<br/>(CURSOR_MODEL_ADVANCED)"]:::runtime
    end

    subgraph "Execution Context"
        FINAL_CFG["Final Configuration<br/>(merged)"]:::runtime
        ORCHESTRATOR["parallel_agent.sh"]:::runtime
    end

    SERVICES --> FINAL_CFG
    COMMAND_CFG --> FINAL_CFG
    VALIDATION --> FINAL_CFG

    REFACTOR_OVER --> FINAL_CFG
    SHELL_OVER --> FINAL_CFG
    DOCS_OVER --> FINAL_CFG

    CLI_ARGS --> FINAL_CFG
    ENV_VARS --> FINAL_CFG

    FINAL_CFG --> ORCHESTRATOR
```

**Configuration Priority (Highest to Lowest):**

1. **CLI Arguments**: `--cursor-model advanced`, `--timeout 900`
2. **Command Overrides**: Per-command settings in `validation_criteria.yml`
3. **Environment Variables**: `CURSOR_MODEL_ADVANCED=gpt-5.2`
4. **Base Configuration**: Default values in `command_config.yml`
5. **Service Toggles**: `services.yml` enabled/disabled flags

**Key Configuration Files:**

- `services.yml`: Which agents are enabled (claude, gemini, cursor)
- `command_config.yml`: Thresholds, model mappings, consensus rules
- `validation_criteria.yml`: Tier 1/2 validation checks and scoring

---

## Cross-Verification Consensus

Algorithm for calculating consensus score between multiple agent outputs.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef high fill:#22c55e,stroke:#166534,color:#fff
    classDef medium fill:#eab308,stroke:#a16207,color:#fff
    classDef low fill:#ef4444,stroke:#dc2626,color:#fff

    START["Agent Outputs<br/>(2 or 3 agents)"]:::input

    COUNT_METRICS["Count Metrics per Agent:<br/>- Issues (bugs, errors, vulnerabilities)<br/>- Warnings (cautions, potential problems)"]:::process

    CALC_AVG["Calculate Averages:<br/>avg_issues = Σ(issues) / agent_count<br/>avg_warnings = Σ(warnings) / agent_count"]:::process

    CALC_DEV["Calculate Total Deviation:<br/>For each agent:<br/>  |issues - avg_issues| + |warnings - avg_warnings|"]:::process

    CALC_CONSENSUS["Consensus Score:<br/>score = ((total_findings - total_deviation) * 100) / total_findings<br/>clamp to [0, 100]"]:::process

    THRESHOLD{"Consensus<br/>Score?"}:::process

    HIGH["HIGH (≥80%)<br/>Auto-proceed with unified recommendation"]:::high
    MEDIUM["MEDIUM (50-79%)<br/>Highlight disagreements to user"]:::medium
    LOW["LOW (<50%)<br/>Block and escalate for human review"]:::low

    START --> COUNT_METRICS
    COUNT_METRICS --> CALC_AVG
    CALC_AVG --> CALC_DEV
    CALC_DEV --> CALC_CONSENSUS
    CALC_CONSENSUS --> THRESHOLD

    THRESHOLD -->|≥80%| HIGH
    THRESHOLD -->|50-79%| MEDIUM
    THRESHOLD -->|<50%| LOW
```

**Consensus Example:**

```
Agent Findings:
- Cursor:  15 issues, 8 warnings  (total: 23)
- Gemini:  12 issues, 10 warnings (total: 22)
- Claude:  14 issues, 9 warnings  (total: 23)

Averages:
- avg_issues = (15+12+14)/3 = 13.67
- avg_warnings = (8+10+9)/3 = 9

Deviations:
- Cursor:  |15-13.67| + |8-9| = 1.33 + 1 = 2.33
- Gemini:  |12-13.67| + |10-9| = 1.67 + 1 = 2.67
- Claude:  |14-13.67| + |9-9| = 0.33 + 0 = 0.33
- Total deviation = 5.33

Consensus Score:
- total_findings = 68
- score = ((68 - 5.33) * 100) / 68 = 92.2%
- Result: HIGH confidence (agents largely agree)
```

---

## Service State Management

State transitions for enabled/disabled services throughout the lifecycle.

```mermaid
%%{init: {'theme':'neutral'}}%%
stateDiagram-v2
    classDef enabled fill:#dcfce7,stroke:#15803d
    classDef disabled fill:#fee2e2,stroke:#dc2626
    classDef warning fill:#fef3c7,stroke:#a16207

    [*] --> DefaultEnabled: bootstrap.sh<br/>initial setup

    DefaultEnabled --> Enabled: services.yml<br/>enabled: true
    DefaultEnabled --> Disabled: services.yml<br/>enabled: false

    Enabled --> TemporaryDisabled: CLI flag<br/>--no-claude
    Enabled --> Running: parallel_agent.sh<br/>executes

    TemporaryDisabled --> Enabled: Next invocation<br/>without flag

    Disabled --> Enabled: Reconfigure<br/>--enable-claude
    Enabled --> Disabled: Reconfigure<br/>--disable-claude

    Running --> Success: Agent completes
    Running --> CreditExhausted: Quota exceeded
    Running --> Failed: Timeout/Error

    CreditExhausted --> FallbackModel: Try cheaper model
    FallbackModel --> Success: Retry succeeds
    FallbackModel --> Failed: All models fail

    Success --> [*]
    Failed --> [*]

    class Enabled enabled
    class Running enabled
    class Success enabled
    class Disabled disabled
    class Failed disabled
    class TemporaryDisabled warning
    class CreditExhausted warning
    class FallbackModel warning
```

**State Transitions:**

1. **Bootstrap**: All services start enabled by default
2. **Configuration**: `services.yml` persists enabled/disabled state
3. **Runtime Override**: CLI flags (`--cursor-only`, `--no-claude`) temporarily modify state
4. **Execution**: Running state while agent processes request
5. **Credit Exhaustion**: Automatic fallback to cheaper models
6. **Reconfiguration**: User can change enabled state via `bootstrap.sh --reconfigure`

**Fallback Chains:**

- **Cursor**: gpt-5.2 → gpt-5.1-codex → gpt-5.1-codex-mini → auto
- **Claude**: opus → sonnet → haiku


---

## Related Documents

- [CLAUDE.md](../CLAUDE.md) - Repository context for AI assistants
- [.claude/CLAUDE.md](../.claude/CLAUDE.md) - Full orchestration guide (deployed to ~/.claude/)
- [README.md](../README.md) - Project overview and quick start
- [GETTING_STARTED.md](GETTING_STARTED.md) - First-time setup walkthrough
- [CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common problems and solutions

---

**Generated by**: `/generate-diagrams` command
**Mermaid Version**: Compatible with GitHub/GitLab markdown renderers
**Last Validated**: 2026-02-04
