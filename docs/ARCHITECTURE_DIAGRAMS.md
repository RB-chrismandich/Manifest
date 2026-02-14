# Architecture Diagrams

> Visual documentation of the Manifest parallel LLM agent orchestration framework

**Last Updated**: 2026-02-13
**Project**: Manifest - AI Agent Orchestration Framework

---

## Table of Contents

1. [Application Architecture](#application-architecture)
2. [Python Parallel Agent Architecture](#python-parallel-agent-architecture)
3. [Git Platform Detection & Operations](#git-platform-detection--operations)
4. [Bootstrap Installation Flow](#bootstrap-installation-flow)
5. [Parallel Agent Execution Flow](#parallel-agent-execution-flow)
6. [Skill Processing Architecture](#skill-processing-architecture)
7. [Validation Pipeline](#validation-pipeline)
8. [Model Selection & Credit Fallback](#model-selection--credit-fallback)
9. [Configuration Layer](#configuration-layer)
10. [Cross-Verification Consensus](#cross-verification-consensus)
11. [Service State Management](#service-state-management)
12. [Issue Management Architecture](#issue-management-architecture)
13. [Label Management Architecture](#label-management-architecture)

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
        VALIDATION_CFG["validation_criteria.yml"]:::config
    end

    subgraph "Orchestration Layer"
        CLAUDE_CLI
        PARALLEL_BASH["parallel_agent.sh<br/>(Bash)"]:::process
        PARALLEL_PY["parallel_agent.py<br/>(Python Phase 3)"]:::process
        GIT_PLATFORM["git_platform.sh"]:::process
        GIT_OPS["git_ops.sh"]:::process
    end

    subgraph "Agent Services"
        GEMINI["Gemini CLI"]:::external
        CURSOR["Cursor Agent"]:::external
        CLAUDE_API["Claude API"]:::external
        CODEX["Codex CLI"]:::external
        GH["GitHub CLI (gh)"]:::external
        GLAB["GitLab CLI (glab)"]:::external
    end

    USER --> BOOTSTRAP
    BOOTSTRAP --> SERVICES
    USER --> CLAUDE_CLI
    CLAUDE_CLI --> PARALLEL_BASH
    CLAUDE_CLI --> PARALLEL_PY
    CLAUDE_CLI --> GIT_OPS
    GIT_OPS --> GIT_PLATFORM
    GIT_PLATFORM -.->|github| GH
    GIT_PLATFORM -.->|gitlab| GLAB
    PARALLEL_BASH --> GEMINI
    PARALLEL_BASH --> CURSOR
    PARALLEL_PY --> GEMINI
    PARALLEL_PY --> CURSOR
    PARALLEL_PY --> CLAUDE_API
    PARALLEL_PY --> CODEX
    SERVICES -.->|config| PARALLEL_BASH
    SERVICES -.->|config| PARALLEL_PY
    COMMAND_CFG -.->|thresholds| PARALLEL_BASH
    COMMAND_CFG -.->|thresholds| PARALLEL_PY
    VALIDATION_CFG -.->|criteria| PARALLEL_PY
```

**Key Components**:

- **bootstrap.sh**: Automated installation and configuration deployment with Python version detection
- **Git Platform Scripts**: Platform-agnostic Git operations (GitHub/GitLab/plain git)
- **parallel_agent.sh**: Bash orchestrator for multiple LLM agents (deprecated — use parallel_agent.py)
- **parallel_agent.py**: Python orchestrator with full feature parity
  (logging, validation, synthesis, streaming, Codex agent, services.yml)
- **Configuration Layer**: YAML files controlling behavior, validation rules, and Phase 3 features
- **Agent Services**: External LLM and Git hosting CLIs

---

## Python Parallel Agent Architecture

Detailed architecture of the Python parallel agent implementation with full feature parity:
comprehensive logging, validation, synthesis, streaming, Codex agent, and services.yml integration.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef active fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef pending fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef error fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef external fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87

    USER["User/Claude CLI"]:::external

    subgraph "Main Orchestrator"
        MAIN["main()"]:::active
        LOGGER["Logger<br/>(correlation IDs, rotation)"]:::active
        CONFIG["Config<br/>(YAML loader)"]:::config
        SVC_CFG["ServiceConfig<br/>(services.yml)"]:::config
        ORCH["Orchestrator"]:::active
    end

    subgraph "Agent Execution"
        BASE["BaseAgent<br/>(rate limiting, timeout, fallback)"]:::active
        CLAUDE_AG["ClaudeAgent<br/>(streaming support)"]:::active
        GEMINI_AG["GeminiAgent<br/>(dual package support)"]:::active
        CURSOR_AG["CursorAgent<br/>(subprocess)"]:::active
        CODEX_AG["CodexAgent<br/>(subprocess, codex exec)"]:::active
    end

    subgraph "Engine Features"
        VALIDATE["ValidationEngine<br/>(Tier 1 + Tier 2)"]:::active
        SYNTH["SynthesisEngine<br/>(disagreement resolution)"]:::active
        STREAM["Streaming Display<br/>(Rich Live)"]:::active
        LIMITER["RateLimiter<br/>(token bucket)"]:::active
    end

    subgraph "External APIs"
        ANTHROPIC["Anthropic API<br/>(Claude)"]:::external
        GOOGLE["Google Gemini API<br/>(OAuth/API key)"]:::external
        CURSOR_CLI["Cursor CLI"]:::external
        CODEX_CLI["Codex CLI"]:::external
    end

    subgraph "Configuration Files"
        PA_YML["parallel_agent.yml<br/>(models, synthesis, streaming)"]:::config
        SVC_YML["services.yml<br/>(agent toggles)"]:::config
        VAL_YML["validation_criteria.yml<br/>(tier1/tier2 rules)"]:::config
        SYNTH_MD["synthesis.md<br/>(prompt template)"]:::config
    end

    subgraph "Outputs"
        LOGS["parallel_agent.log<br/>(JSON structured)"]:::pending
        RESULTS["results_*.json<br/>(agent outputs)"]:::pending
        SUMMARY["summary_*.md<br/>(markdown report)"]:::pending
    end

    USER --> MAIN
    MAIN --> CONFIG
    MAIN --> SVC_CFG
    MAIN --> LOGGER
    MAIN --> ORCH
    CONFIG -.->|load| PA_YML
    SVC_CFG -.->|load| SVC_YML
    LOGGER -.->|write| LOGS

    ORCH --> VALIDATE
    ORCH --> SYNTH
    ORCH --> STREAM
    ORCH --> BASE

    BASE --> LIMITER
    BASE --> CLAUDE_AG
    BASE --> GEMINI_AG
    BASE --> CURSOR_AG
    BASE --> CODEX_AG

    CLAUDE_AG --> ANTHROPIC
    GEMINI_AG --> GOOGLE
    CURSOR_AG --> CURSOR_CLI
    CODEX_AG --> CODEX_CLI

    VALIDATE -.->|load| VAL_YML
    SYNTH -.->|load| SYNTH_MD
    SYNTH --> ANTHROPIC

    ORCH -.->|write| RESULTS
    ORCH -.->|write| SUMMARY

    STREAM -.->|display| USER
```

**Components**:

- **ServiceConfig**: Reads `services.yml` for agent enable/disable state, minimum agent validation
- **Logger**: Structured JSON logging with correlation IDs (`YYYYMMDD_HHMMSS_PID`),
  rotating file handler (10MB, 5 backups), performance metrics
- **ValidationEngine**:
  - Tier 1 (critical): Security, error handling, breaking changes, cross-verification
  - Tier 2 (quality): Bug detection, performance, maintainability, test coverage
  - Verdicts: APPROVED, NEEDS_REVIEW, BLOCKED
- **SynthesisEngine**: Automatic disagreement resolution when consensus < 50%, uses Claude Sonnet with synthesis.md template
- **Streaming**: Real-time Rich Live display with progressive updates (4 updates/sec, 500 char truncation)
- **RateLimiter**: Token bucket algorithm with burst support and adaptive backoff
- **CodexAgent**: Subprocess-based agent using `codex exec` with `--output-last-message` for reliable output capture
- **Dual Package Support**: google-genai (new) with fallback to google-generativeai (legacy), unified interface

**Execution Flow**:

1. **Initialization**: Load config + services.yml, create logger with correlation ID, set up rate limiters
2. **Agent Selection**: services.yml state -> `--*-only` exclusive flags -> `--no-*` overrides -> minimum agent check
3. **Agent Execution**: Run Claude/Gemini/Cursor/Codex in parallel with streaming or progress display
4. **Consensus**: Calculate consensus score using keyword-based analysis
5. **Synthesis**: If consensus < 50%, trigger SynthesisEngine for unified recommendation
6. **Validation**: Run ValidationEngine if `--validate` flag set
7. **Output**: Write structured logs, JSON results (with duration), markdown summary (sandbox-aware fallback)

**Statistics**:

- Classes: 11 (Config, ServiceConfig, Logger, RateLimiter, ValidationEngine, SynthesisEngine,
  BaseAgent, ClaudeAgent, GeminiAgent, CursorAgent, CodexAgent, Orchestrator)
- CLI Flags: 27 (--codex-only, --codex-model, --no-cursor, --no-gemini, --no-codex, --status added)
- Agents: 4 (Claude, Gemini, Cursor, Codex)

---

## Git Platform Detection & Operations

Platform-agnostic Git operations flow with automatic platform detection and routing to appropriate CLI tools.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef github fill:#24292f,stroke:#0969da,color:#fff
    classDef gitlab fill:#fc6d26,stroke:#e24329,color:#fff
    classDef fallback fill:#fef3c7,stroke:#d97706,color:#78350f

    COMMAND["User Command<br/>(issue-view, pr-create, etc.)"]:::input
    GIT_OPS["git_ops.sh"]:::process
    GIT_PLATFORM["git_platform.sh"]:::process

    subgraph "Platform Detection"
        ENV_OVERRIDE["Check ENV vars<br/>(MANIFEST_GIT_PLATFORM)"]:::process
        REMOTE_URL["Parse git remote URL"]:::process
        PATTERN_MATCH["URL Pattern Match"]:::process
        ENV_OVERRIDE --> REMOTE_URL
        REMOTE_URL --> PATTERN_MATCH
    end

    GH_CLI["GitHub CLI (gh)<br/>gh issue view, gh pr create"]:::github
    GLAB_CLI["GitLab CLI (glab)<br/>glab issue view, glab mr create"]:::gitlab
    PLAIN_GIT["Plain Git<br/>(warn + suggest install)"]:::fallback

    COMMAND --> GIT_OPS
    GIT_OPS --> GIT_PLATFORM
    GIT_PLATFORM --> ENV_OVERRIDE

    PATTERN_MATCH -->|github.com| GH_CLI
    PATTERN_MATCH -->|gitlab.com / gitlab.*| GLAB_CLI
    PATTERN_MATCH -->|other| PLAIN_GIT

    GH_CLI --> RESULT["Result"]:::input
    GLAB_CLI --> RESULT
    PLAIN_GIT --> RESULT
```

**Detection Logic**:

1. **Environment Override**: `MANIFEST_GIT_PLATFORM` forces specific platform
2. **Remote URL Parsing**: Reads `git remote get-url origin` (or `$MANIFEST_GIT_REMOTE`)
3. **Pattern Matching**:
   - `*github.com*` → GitHub (gh)
   - `*gitlab.com*` or `*gitlab.*` → GitLab (glab)
   - Other → Plain git (warn)

**Subcommand Mapping**:

| Generic | GitHub (gh) | GitLab (glab) |
|---------|-------------|---------------|
| issue-comment | gh issue comment | glab issue note |
| issue-edit | gh issue edit | glab issue update |
| pr-create | gh pr create | glab mr create |
| pr-view | gh pr view | glab mr view |

---

## Bootstrap Installation Flow

Complete installation and configuration deployment process with Git CLI auto-detection.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef success fill:#22c55e,stroke:#166534,color:#fff
    classDef skip fill:#e5e7eb,stroke:#6b7280,color:#374151

    START["./bootstrap.sh"]:::input
    PARSE_ARGS["Parse CLI Arguments<br/>(--enable/--disable flags)"]:::process
    DETECT_PLATFORM["Detect OS Platform<br/>(macOS, Linux distro)"]:::process

    LOAD_CONFIG{"Load Existing<br/>services.yml?"}:::decision
    MERGE_CONFIG["Merge File Config<br/>with CLI Args"]:::process

    INSTALL_PKG["Install Package Manager<br/>(Homebrew on macOS)"]:::process
    INSTALL_NODE["Install Node.js<br/>(for npm CLIs)"]:::process

    CHECK_CLAUDE{"Claude<br/>Enabled?"}:::decision
    INSTALL_CLAUDE["Install Claude CLI<br/>(npm install -g)"]:::process
    SKIP_CLAUDE["Skip Claude"]:::skip

    CHECK_GEMINI{"Gemini<br/>Enabled?"}:::decision
    INSTALL_GEMINI["Install Gemini CLI<br/>(npm install -g)"]:::process
    SKIP_GEMINI["Skip Gemini"]:::skip

    CHECK_GH{"GitHub CLI<br/>Enabled/Auto?"}:::decision
    AUTO_GH{"gh already<br/>installed?"}:::decision
    INSTALL_GH["Install GitHub CLI<br/>(brew/apt/dnf)"]:::process
    SKIP_GH["Disable GitHub CLI"]:::skip

    CHECK_GLAB{"GitLab CLI<br/>Enabled/Auto?"}:::decision
    AUTO_GLAB{"glab already<br/>installed?"}:::decision
    INSTALL_GLAB["Install GitLab CLI<br/>(brew/apt/dnf)"]:::process
    SKIP_GLAB["Disable GitLab CLI"]:::skip

    CHECK_JQ["Check jq<br/>(required by git_ops.sh)"]:::process
    INSTALL_JQ["Install jq"]:::process

    CHECK_CURSOR{"Cursor<br/>Enabled?"}:::decision
    OPEN_CURSOR["Open Cursor<br/>Download Page"]:::process
    SKIP_CURSOR["Skip Cursor"]:::skip

    DEPLOY["Deploy Config Files<br/>(~/.claude, ~/.cursor, ~/.gemini)"]:::process
    WRITE_SERVICES["Write services.yml<br/>(with final toggles)"]:::process

    AUTH_CLAUDE["Setup Claude Auth"]:::process
    AUTH_GEMINI["Setup Gemini Auth"]:::process
    AUTH_GH["Setup GitHub Auth<br/>(gh auth login)"]:::process
    AUTH_GLAB["Setup GitLab Auth<br/>(glab auth login)"]:::process

    VERIFY["Verify Installation<br/>(check files, CLIs, scripts)"]:::process
    DONE["Installation Complete"]:::success

    START --> PARSE_ARGS
    PARSE_ARGS --> DETECT_PLATFORM
    DETECT_PLATFORM --> LOAD_CONFIG

    LOAD_CONFIG -->|Yes| MERGE_CONFIG
    LOAD_CONFIG -->|No| INSTALL_PKG
    MERGE_CONFIG --> INSTALL_PKG

    INSTALL_PKG --> INSTALL_NODE
    INSTALL_NODE --> CHECK_CLAUDE

    CHECK_CLAUDE -->|Yes| INSTALL_CLAUDE
    CHECK_CLAUDE -->|No| SKIP_CLAUDE
    INSTALL_CLAUDE --> CHECK_GEMINI
    SKIP_CLAUDE --> CHECK_GEMINI

    CHECK_GEMINI -->|Yes| INSTALL_GEMINI
    CHECK_GEMINI -->|No| SKIP_GEMINI
    INSTALL_GEMINI --> CHECK_GH
    SKIP_GEMINI --> CHECK_GH

    CHECK_GH -->|Enabled| INSTALL_GH
    CHECK_GH -->|Auto| AUTO_GH
    CHECK_GH -->|Disabled| SKIP_GH
    AUTO_GH -->|Yes| SKIP_GH
    AUTO_GH -->|No| SKIP_GH
    INSTALL_GH --> CHECK_GLAB
    SKIP_GH --> CHECK_GLAB

    CHECK_GLAB -->|Enabled| INSTALL_GLAB
    CHECK_GLAB -->|Auto| AUTO_GLAB
    CHECK_GLAB -->|Disabled| SKIP_GLAB
    AUTO_GLAB -->|Yes| SKIP_GLAB
    AUTO_GLAB -->|No| SKIP_GLAB
    INSTALL_GLAB --> CHECK_JQ
    SKIP_GLAB --> CHECK_JQ

    CHECK_JQ -->|Not Found| INSTALL_JQ
    CHECK_JQ -->|Found| CHECK_CURSOR
    INSTALL_JQ --> CHECK_CURSOR

    CHECK_CURSOR -->|Yes| OPEN_CURSOR
    CHECK_CURSOR -->|No| SKIP_CURSOR
    OPEN_CURSOR --> DEPLOY
    SKIP_CURSOR --> DEPLOY

    DEPLOY --> WRITE_SERVICES
    WRITE_SERVICES --> AUTH_CLAUDE
    AUTH_CLAUDE --> AUTH_GEMINI
    AUTH_GEMINI --> AUTH_GH
    AUTH_GH --> AUTH_GLAB
    AUTH_GLAB --> VERIFY
    VERIFY --> DONE
```

**Key Features**:

- **Auto-Detection**: gh/glab default to `auto` mode (enable if already installed)
- **Platform-Specific Install**: Uses appropriate package manager (brew/apt/dnf/pacman)
- **Dependency Checking**: Verifies jq is installed (required for git_ops.sh JSON normalization)
- **Service Toggles**: Writes final enabled/disabled state to services.yml

---

## Parallel Agent Execution Flow

How multiple LLM agents are orchestrated for cross-verification with consensus scoring,
including sandbox detection and output verification.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef active fill:#22c55e,stroke:#166534,color:#fff
    classDef warning fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff

    START["Task Input<br/>(code review, analysis, planning)"]:::input
    PARSE["Parse Arguments<br/>(--review, --analyze, --improve)"]:::process

    SANDBOX_CHECK{"Output Dir<br/>Writable?"}:::decision
    DEFAULT_DIR["Use ~/.claude/.agent_outputs"]:::process
    FALLBACK_DIR["Fallback to /tmp/.claude_agent_outputs_$$"]:::warning

    CHECK_SERVICES{"Check<br/>services.yml"}:::decision

    subgraph "Agent Execution (Parallel)"
        GEMINI_EXEC["Gemini CLI<br/>(gemini-3-flash/pro)"]:::process
        CURSOR_EXEC["Cursor Agent<br/>(gpt-5.1/5.2)"]:::process
        CLAUDE_EXEC["Claude CLI<br/>(haiku/sonnet/opus)"]:::process
        CODEX_EXEC["Codex CLI<br/>(o4-mini/o3/o3-pro)"]:::process
    end

    COLLECT["Collect Outputs<br/>(with retry + fallback)"]:::process

    VERIFY_FILES{"Output Files<br/>Created?"}:::decision
    FILE_ERROR["Exit with Error<br/>(code 13)"]:::error

    VALIDATE{"Validation<br/>Enabled?"}:::decision
    CHECK_CRITERIA["Check Success Criteria<br/>(from validation_criteria.yml)"]:::process

    CONSENSUS["Calculate Consensus Score<br/>(agreement / total findings * 100)"]:::process

    SCORE_CHECK{"Consensus<br/>Score?"}:::decision

    HIGH["High Confidence (≥80%)<br/>Proceed with unified recommendation"]:::active
    MEDIUM["Medium Confidence (50-79%)<br/>Highlight disagreements"]:::warning
    LOW["Low Confidence (<50%)<br/>Escalate for human review"]:::error

    OUTPUT["Generate JSON Output<br/>(agents, consensus, validation)"]:::process
    SUMMARY["Create Markdown Summary"]:::process
    DONE["Return Results"]:::input

    START --> PARSE
    PARSE --> SANDBOX_CHECK
    SANDBOX_CHECK -->|Yes| DEFAULT_DIR
    SANDBOX_CHECK -->|No| FALLBACK_DIR
    DEFAULT_DIR --> CHECK_SERVICES
    FALLBACK_DIR --> CHECK_SERVICES

    CHECK_SERVICES --> GEMINI_EXEC
    CHECK_SERVICES --> CURSOR_EXEC
    CHECK_SERVICES --> CLAUDE_EXEC
    CHECK_SERVICES --> CODEX_EXEC

    GEMINI_EXEC --> COLLECT
    CURSOR_EXEC --> COLLECT
    CLAUDE_EXEC --> COLLECT
    CODEX_EXEC --> COLLECT

    COLLECT --> VERIFY_FILES
    VERIFY_FILES -->|No| FILE_ERROR
    VERIFY_FILES -->|Yes| VALIDATE

    VALIDATE -->|Yes| CHECK_CRITERIA
    VALIDATE -->|No| CONSENSUS
    CHECK_CRITERIA --> CONSENSUS

    CONSENSUS --> SCORE_CHECK
    SCORE_CHECK -->|≥80%| HIGH
    SCORE_CHECK -->|50-79%| MEDIUM
    SCORE_CHECK -->|<50%| LOW

    HIGH --> OUTPUT
    MEDIUM --> OUTPUT
    LOW --> OUTPUT

    OUTPUT --> SUMMARY
    SUMMARY --> DONE
```

**Execution Model**:

- **Sandbox Detection**: Auto-detects write restrictions and falls back to `/tmp` if needed
- **Parallel Execution**: All enabled agents run simultaneously via background processes
- **Output Verification**: Explicit check that files were created before proceeding
- **Retry Logic**: Failed agents retry once after 5s delay
- **Credit Fallback**: Automatically retries with cheaper models on quota errors
- **Partial Results**: Continues with available agents if some fail

**Sandbox Handling** (New in 2026-02-06):

When running in sandboxed environments (e.g., Task subagents):

1. Script tests if `~/.claude/.agent_outputs` is writable
2. Falls back to `/tmp/.claude_agent_outputs_$$` if restricted
3. Verifies output files exist after agents complete
4. Exit code 13 if no files created (with helpful error message)

**Consensus Calculation**:

```text
Consensus Score = (Agreements / Total_Findings) * 100

≥80%: High confidence (auto-proceed)
50-79%: Medium confidence (show disagreements)
<50%: Low confidence (user decision required)
```

---

## Skill Processing Architecture

How slash commands (skills) are processed from user input to execution with parallel agent integration.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef external fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User: /skill-name args"]:::input

    subgraph "Skill Layer"
        PARSE["Parse Skill & Args"]:::process
        LOAD_CMD["Load Skill Definition<br/>(SKILL.md)"]:::process
    end

    subgraph "Preflight Analysis"
        CHECK_CRITERIA{"Meets Parallel<br/>Agent Criteria?"}:::decision
        TRIGGER["Trigger Conditions:<br/>- Security-sensitive<br/>- Architecture changes<br/>- Large scope (3+ files)<br/>- Critical logic"]:::process
    end

    subgraph "Execution"
        SINGLE["Single Agent Execution"]:::process
        PARALLEL["Parallel Agent Execution<br/>(parallel_agent.sh)"]:::external
    end

    subgraph "Post-Processing"
        SYNTHESIS{"Consensus<br/>< 80%?"}:::decision
        SYNTH_AGENT["Synthesis Agent<br/>(resolve disagreements)"]:::external
        VALIDATION["Validation Agent<br/>(check against criteria)"]:::external
    end

    OUTPUT["Return Result to User"]:::input

    USER --> PARSE
    PARSE --> LOAD_CMD
    LOAD_CMD --> CHECK_CRITERIA

    CHECK_CRITERIA -->|Yes| PARALLEL
    CHECK_CRITERIA -->|No| SINGLE

    PARALLEL --> SYNTHESIS
    SINGLE --> OUTPUT

    SYNTHESIS -->|Yes| SYNTH_AGENT
    SYNTHESIS -->|No| VALIDATION
    SYNTH_AGENT --> VALIDATION
    VALIDATION --> OUTPUT
```

**Command Types**:

- **ALWAYS Parallel**: `/refactor-python`, `/refactor-shell` (security-sensitive)
- **CONDITIONAL**: `/docs-diagrams` (5+ modules), `/plan-manage` (complex planning),
  `/browser-test` (critical flows, 3+ tests)
- **NEVER Parallel**: `/docs-readme` (straightforward documentation)

---

## Validation Pipeline

How code changes and agent outputs are validated against Tier 1 (critical) and Tier 2 (quality) criteria.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef tier1 fill:#ef4444,stroke:#dc2626,color:#fff
    classDef tier2 fill:#eab308,stroke:#a16207,color:#fff
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef success fill:#22c55e,stroke:#166534,color:#fff
    classDef blocked fill:#dc2626,stroke:#991b1b,color:#fff

    CODE["Code/Agent Output"]:::input
    LOAD_CRITERIA["Load validation_criteria.yml"]:::process

    subgraph "Tier 1: Critical Checks (Blocking)"
        CROSS_VERIFY["Cross-Verification<br/>(weight: 0.3)"]:::tier1
        SECURITY["Security Issues<br/>(weight: 0.3)"]:::tier1
        ERROR_HANDLE["Error Handling<br/>(weight: 0.2)"]:::tier1
        BREAKING["Breaking Changes<br/>(weight: 0.2)"]:::tier1
    end

    TIER1_CHECK{"All Tier 1<br/>Pass?"}:::tier1
    BLOCKED_VERDICT["VERDICT: BLOCKED"]:::blocked

    subgraph "Tier 2: Quality Checks (Advisory)"
        BUG_DETECT["Bug Detection<br/>(weight: 0.25)"]:::tier2
        PERFORMANCE["Performance<br/>(weight: 0.25)"]:::tier2
        MAINTAIN["Maintainability<br/>(weight: 0.25)"]:::tier2
        TEST_COV["Test Coverage<br/>(weight: 0.25)"]:::tier2
    end

    TIER2_SCORE["Calculate Tier 2 Score<br/>(weighted sum)"]:::process

    TIER2_CHECK{"Score<br/>≥ 0.60?"}:::tier2

    APPROVED["VERDICT: APPROVED"]:::success
    NEEDS_REVIEW["VERDICT: NEEDS_REVIEW"]:::tier2

    CODE --> LOAD_CRITERIA
    LOAD_CRITERIA --> CROSS_VERIFY
    CROSS_VERIFY --> SECURITY
    SECURITY --> ERROR_HANDLE
    ERROR_HANDLE --> BREAKING
    BREAKING --> TIER1_CHECK

    TIER1_CHECK -->|Yes| BUG_DETECT
    TIER1_CHECK -->|No| BLOCKED_VERDICT

    BUG_DETECT --> PERFORMANCE
    PERFORMANCE --> MAINTAIN
    MAINTAIN --> TEST_COV
    TEST_COV --> TIER2_SCORE
    TIER2_SCORE --> TIER2_CHECK

    TIER2_CHECK -->|Yes| APPROVED
    TIER2_CHECK -->|No| NEEDS_REVIEW
```

**Validation Verdicts**:

- **APPROVED**: All Tier 1 pass, Tier 2 ≥ 0.60 → Safe to proceed
- **NEEDS_REVIEW**: All Tier 1 pass, Tier 2 < 0.60 → Manual review recommended
- **BLOCKED**: Any Tier 1 fails → Changes rejected

**Command-Specific Overrides**:
Commands can override default thresholds in `validation_criteria.yml`:

```yaml
command_overrides:
  refactor-python:
    tier1:
      security_issues: 0.5  # Higher weight for Python security
  project-commit:
    tier2:
      test_coverage: 0.0    # Don't require tests for commits
```

---

## Model Selection & Credit Fallback

Automatic model tier selection and graceful fallback when quota/credits are exhausted.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef fallback fill:#eab308,stroke:#a16207,color:#fff
    classDef error fill:#ef4444,stroke:#dc2626,color:#fff

    TASK["Task Type"]:::input

    CLASSIFY{"Task<br/>Classification"}:::decision

    SECURITY["Security Review<br/>(auth, crypto, secrets)"]:::process
    REVIEW["Code Review<br/>(general changes)"]:::process
    ANALYZE["Analysis<br/>(bugs, patterns)"]:::process
    IMPROVE["Improvements<br/>(docs, suggestions)"]:::process
    QUICK["Quick Query<br/>(simple questions)"]:::process

    SEC_MODELS["Cursor: advanced<br/>Claude: opus<br/>Gemini: pro"]:::process
    REV_MODELS["Cursor: flash<br/>Claude: sonnet<br/>Gemini: flash"]:::process
    ANA_MODELS["Cursor: flash<br/>Claude: sonnet<br/>Gemini: flash"]:::process
    IMP_MODELS["Cursor: mini<br/>Claude: haiku<br/>Gemini: flash"]:::process
    QCK_MODELS["Cursor: mini<br/>Claude: haiku<br/>Gemini: flash"]:::process

    EXECUTE["Execute with Selected Models"]:::process

    CHECK_ERROR{"Credit/Quota<br/>Error?"}:::decision

    FALLBACK["Fallback to Cheaper Model"]:::fallback
    RETRY["Retry with Fallback"]:::process

    SUCCESS["Return Results"]:::input
    FAIL["Report Error<br/>(all fallbacks exhausted)"]:::error

    TASK --> CLASSIFY

    CLASSIFY -->|Security| SECURITY
    CLASSIFY -->|Review| REVIEW
    CLASSIFY -->|Analyze| ANALYZE
    CLASSIFY -->|Improve| IMPROVE
    CLASSIFY -->|Quick| QUICK

    SECURITY --> SEC_MODELS
    REVIEW --> REV_MODELS
    ANALYZE --> ANA_MODELS
    IMPROVE --> IMP_MODELS
    QUICK --> QCK_MODELS

    SEC_MODELS --> EXECUTE
    REV_MODELS --> EXECUTE
    ANA_MODELS --> EXECUTE
    IMP_MODELS --> EXECUTE
    QCK_MODELS --> EXECUTE

    EXECUTE --> CHECK_ERROR

    CHECK_ERROR -->|Yes| FALLBACK
    CHECK_ERROR -->|No| SUCCESS

    FALLBACK --> RETRY
    RETRY --> CHECK_ERROR

    FALLBACK -.->|All fallbacks tried| FAIL
```

**Cursor Fallback Chain**:

```text
gpt-5.2 (advanced) → gpt-5.1-codex (flash) → gpt-5.1-codex-mini (mini) → auto
```

**Claude Fallback Chain**:

```text
opus → sonnet → haiku
```

**Codex Fallback Chain**:

```text
o3-pro (advanced) → o3 (flash) → o4-mini (mini)
```

**Error Detection**:
The script parses stderr for patterns:

- "credit", "quota", "rate limit", "insufficient"
- Automatically retries with next cheaper model
- Continues with available agents if one exhausts credits

---

## Configuration Layer

How YAML configuration files control behavior, thresholds, and service toggles.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef output fill:#fef3c7,stroke:#d97706,color:#78350f

    BOOTSTRAP["bootstrap.sh"]:::process

    subgraph "Configuration Files"
        SERVICES["services.yml<br/>(Claude, Gemini, Cursor, Codex,<br/>GitHub CLI, GitLab CLI)"]:::config
        COMMAND_CFG["command_config.yml<br/>(Thresholds, Tool Policies,<br/>Model Selection)"]:::config
        VALIDATION["validation_criteria.yml<br/>(Tier 1/2 Criteria,<br/>Command Overrides)"]:::config
    end

    PARSE_SERVICES["Parse Service Toggles<br/>(awk parser)"]:::process
    PARSE_COMMAND["Load Command Config<br/>(YAML parser)"]:::process
    PARSE_VALID["Load Validation Rules<br/>(YAML parser)"]:::process

    PARALLEL["parallel_agent.sh"]:::process
    COMMANDS["Command Execution"]:::process
    VALIDATORS["Validation Agents"]:::process

    BOOTSTRAP --> SERVICES
    SERVICES --> PARSE_SERVICES
    PARSE_SERVICES --> PARALLEL

    COMMAND_CFG --> PARSE_COMMAND
    PARSE_COMMAND --> PARALLEL
    PARSE_COMMAND --> COMMANDS

    VALIDATION --> PARSE_VALID
    PARSE_VALID --> VALIDATORS
    PARSE_VALID --> PARALLEL

    PARALLEL --> RESULT["Agent Outputs"]:::output
    COMMANDS --> RESULT
    VALIDATORS --> RESULT
```

**services.yml Structure**:

```yaml
services:
  claude:
    enabled: true
    command: claude
  gemini:
    enabled: true
    command: gemini
  cursor:
    enabled: true
    command: cursor
  git_cli:
    github:
      enabled: auto  # auto-detect
      command: gh
    gitlab:
      enabled: auto
      command: glab
    detection:
      platform: auto
      remote: origin
```

**Key Features**:

- **Service Toggles**: Enable/disable agents and Git CLIs
- **Auto-Detection**: gh/glab default to `auto` (enable if installed)
- **Nested Configuration**: git_cli section contains github/gitlab subsections
- **Reconfigurable**: `bootstrap.sh --reconfigure` updates toggles without reinstall

---

## Cross-Verification Consensus

How agent outputs are compared and consensus scores are calculated for decision-making.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef high fill:#22c55e,stroke:#166534,color:#fff
    classDef medium fill:#eab308,stroke:#a16207,color:#fff
    classDef low fill:#ef4444,stroke:#dc2626,color:#fff

    OUTPUTS["Agent Outputs<br/>(Gemini, Cursor, Claude)"]:::input

    EXTRACT["Extract Key Findings<br/>(Issues, Recommendations, Risks)"]:::process

    COMPARE["Compare Findings Across Agents"]:::process

    COUNT_AGREE["Count Agreements<br/>(Same finding from 2+ agents)"]:::process
    COUNT_TOTAL["Count Total Unique Findings"]:::process

    CALC["Calculate Consensus Score<br/>(Agreements / Total * 100)"]:::process

    SCORE_CHECK{"Consensus<br/>Score?"}:::process

    HIGH["≥80% - High Confidence<br/>✓ Unified recommendation<br/>✓ Auto-proceed"]:::high
    MEDIUM["50-79% - Medium Confidence<br/>⚠ Show disagreements<br/>⚠ User review recommended"]:::medium
    LOW["<50% - Low Confidence<br/>✗ Escalate to user<br/>✗ Manual decision required"]:::low

    OUTPUTS --> EXTRACT
    EXTRACT --> COMPARE
    COMPARE --> COUNT_AGREE
    COMPARE --> COUNT_TOTAL
    COUNT_AGREE --> CALC
    COUNT_TOTAL --> CALC
    CALC --> SCORE_CHECK

    SCORE_CHECK -->|≥80%| HIGH
    SCORE_CHECK -->|50-79%| MEDIUM
    SCORE_CHECK -->|<50%| LOW
```

**Example Consensus Calculation**:

Given 3 agents with these findings:

- **Gemini**: [A, B, C, D]
- **Cursor**: [A, B, E]
- **Claude**: [A, C, F]

**Analysis**:

- Total unique findings: A, B, C, D, E, F = **6**
- Agreements (2+ agents):
  - A: all 3 agents ✓
  - B: Gemini + Cursor ✓
  - C: Gemini + Claude ✓
- Agreement count: **3**
- **Consensus Score**: 3/6 * 100 = **50%** (MEDIUM)

**Action**: Show disagreements (D, E, F are unique to single agents), recommend user review.

---

## Service State Management

Lifecycle and state transitions of enabled services throughout the framework.

```mermaid
%%{init: {'theme':'neutral'}}%%
stateDiagram-v2
    classDef enabled fill:#22c55e,stroke:#166534,color:#fff
    classDef disabled fill:#e5e7eb,stroke:#6b7280,color:#374151
    classDef auto fill:#3b82f6,stroke:#1d4ed8,color:#fff

    [*] --> NotInstalled

    NotInstalled --> Auto: Default (gh/glab)
    NotInstalled --> Disabled: --disable flag
    NotInstalled --> Enabled: --enable flag

    Auto --> Enabled: CLI detected
    Auto --> Disabled: CLI not found

    Enabled --> Available: Auth successful
    Enabled --> Unavailable: Auth failed / CLI missing

    Available --> InUse: Command execution
    InUse --> Available: Command complete

    Unavailable --> Available: Install + Auth

    Disabled --> Enabled: --enable flag
    Enabled --> Disabled: --disable flag

    Available --> [*]: Uninstall
    Disabled --> [*]: Uninstall

    class Enabled,Available,InUse enabled
    class Disabled,Unavailable,NotInstalled disabled
    class Auto auto
```

**State Descriptions**:

- **NotInstalled**: Service not yet configured (initial state)
- **Auto**: Auto-detect mode (default for gh/glab)
- **Enabled**: Explicitly enabled by user
- **Disabled**: Explicitly disabled by user
- **Available**: CLI installed and authenticated (ready for use)
- **Unavailable**: Enabled but CLI missing or auth failed
- **InUse**: Currently executing a command

**Transitions**:

- `bootstrap.sh` initializes state based on flags and detection
- `services.yml` persists state across sessions
- `bootstrap.sh --reconfigure` allows state changes without reinstall

---

## Issue Management Architecture

Shows the two issue management commands and how they interact with different platforms.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef output fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef platform fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef agent fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User"]:::input

    subgraph "Issue Commands"
        PRIORITIZE["/issue-prioritize<br/>Read-only ranking"]:::process
        TRIAGE["/issue-triage<br/>Backlog hygiene"]:::process
    end

    subgraph "Platform Detection"
        DETECT["git_platform.sh"]:::process
        GH["GitHub (gh)"]:::platform
        GL["GitLab (glab)"]:::platform
        LIN["Linear (linear_ops.sh)"]:::platform
        DETECT --> GH
        DETECT --> GL
        DETECT --> LIN
    end

    subgraph "Issue Prioritization Flow"
        FETCH["Fetch Open Issues"]:::process
        FILTER["Filter Excluded Labels"]:::process
        HEURISTIC["Heuristic Pre-Scoring<br/>Impact × 3 + Urgency × 2<br/>+ Readiness × 2 - Risk"]:::process
        AGENT_REFINE["Agent-Refined Scoring<br/>(top 5-7 only)"]:::agent
        RANK["Rank & Tiebreak"]:::process
        REPORT["Prioritization Report"]:::output
        FETCH --> FILTER --> HEURISTIC --> AGENT_REFINE --> RANK --> REPORT
    end

    subgraph "Issue Triage Flow"
        FETCH_LIN["Fetch Linear Issues"]:::process
        DUP["Duplicate Detection<br/>Fuzzy title matching"]:::process
        STALE["Staleness Detection<br/>File refs + inactivity"]:::process
        PRI_VAL["Priority Validation<br/>Agent consensus"]:::agent
        TRIAGE_REPORT["Triage Report + Actions"]:::output
        FETCH_LIN --> DUP --> STALE --> PRI_VAL --> TRIAGE_REPORT
    end

    USER --> PRIORITIZE
    USER --> TRIAGE
    PRIORITIZE --> DETECT
    GH --> FETCH
    GL --> FETCH
    LIN --> FETCH
    TRIAGE --> FETCH_LIN
    LIN --> FETCH_LIN
```

**Key differences**:

- **issue-prioritize**: Multi-platform (GitHub, GitLab, Linear), read-only, scoring-focused
- **issue-triage**: Linear-only, performs mutations (mark duplicates, close stale), hygiene-focused

**Scoring formula**: `Priority Score = (Impact × 3) + (Urgency × 2) + (Readiness × 2) - Risk`

**Tiebreakers**: bugs > features, unblockers > isolated, planned > unplanned, older > newer

---

## Label Management Architecture

How the canonical label registry drives consistent label provisioning across GitHub, GitLab, and Linear.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef registry fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef script fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef platform fill:#3b82f6,stroke:#1d4ed8,color:#fff
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef output fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e

    LABELS["labels.yml<br/>(canonical registry)"]:::registry

    subgraph "Label Sync Engine (label_sync.sh)"
        PARSE["Parse YAML<br/>(python3)"]:::script
        FILTER{"Platform<br/>Filter?"}:::decision
        VALIDATE["Validate Fields<br/>(name, color, platforms)"]:::script
        DRY_CHECK{"--dry-run?"}:::decision
        DRY_OUT["Report would-create<br/>actions"]:::output
        PROVISION["Create Label<br/>on Target Platform"]:::script
    end

    subgraph "Target Platforms"
        GH["GitHub<br/>gh label create"]:::platform
        GL["GitLab<br/>glab label create"]:::platform
        LIN["Linear<br/>linear_ops.sh label-create"]:::platform
    end

    subgraph "Consumers"
        PLAN["/plan-manage<br/>planned, in-progress, done"]:::script
        TRIAGE["/issue-triage<br/>needs-review, follow-up"]:::script
        HEALTH["/health-check<br/>label validation"]:::script
    end

    LABELS --> PARSE
    PARSE --> FILTER
    FILTER -->|Yes| VALIDATE
    FILTER -->|No| VALIDATE
    VALIDATE --> DRY_CHECK
    DRY_CHECK -->|Yes| DRY_OUT
    DRY_CHECK -->|No| PROVISION
    PROVISION --> GH
    PROVISION --> GL
    PROVISION --> LIN
    LABELS --> PLAN
    LABELS --> TRIAGE
    LABELS --> HEALTH
```

**Canonical Labels** (5 labels, 3 platforms):

| Label | Color | Platforms | Used By |
|-------|-------|-----------|---------|
| `planned` | `#1D76DB` (Blue) | GitHub, GitLab, Linear | /plan-manage create |
| `in-progress` | `#FBCA04` (Yellow) | GitHub, GitLab, Linear | /plan-manage execute |
| `needs-review` | `#E3A21A` (Orange) | GitHub, GitLab, Linear | /issue-triage |
| `done` | `#0E8A16` (Green) | GitHub, GitLab, Linear | /plan-manage execute |
| `follow-up` | `#D4C5F9` (Lavender) | GitHub, GitLab, Linear | /issue-triage |
| `future` | `#C2E0C6` (Green) | GitHub, GitLab, Linear | /issue-prioritize |

**Deprecated**: `processed` (replaced by `done`)

**Sync Modes**:

- `--dry-run`: Report what would be created without making changes
- `--validate`: Alias for `--dry-run` (validation only)
- `--platform <name>`: Restrict sync to a single platform (github, gitlab, linear)

---

## Related Documents

- [AGENTS.md](../AGENTS.md) - AI agent instructions for all platforms
- [CLAUDE.md](../CLAUDE.md) - Claude Code project instructions
- [README.md](../README.md) - Project overview and quick start
- [docs/GETTING_STARTED.md](GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common problems and solutions
- [configs/claude/.plans/README.md](../configs/claude/.plans/README.md) - Plan management quick reference
