# Architecture Diagrams

> Visual documentation of the Manifest parallel LLM agent orchestration framework

**Last Updated**: 2026-02-06 (Added sandbox detection & output verification to Parallel Agent flow)
**Project**: Manifest - AI Agent Orchestration Framework

---

## Table of Contents

1. [Application Architecture](#application-architecture)
2. [Git Platform Detection & Operations](#git-platform-detection--operations)
3. [Bootstrap Installation Flow](#bootstrap-installation-flow)
4. [Parallel Agent Execution Flow](#parallel-agent-execution-flow)
5. [Command Processing Architecture](#command-processing-architecture)
6. [Validation Pipeline](#validation-pipeline)
7. [Model Selection & Credit Fallback](#model-selection--credit-fallback)
8. [Configuration Layer](#configuration-layer)
9. [Cross-Verification Consensus](#cross-verification-consensus)
10. [Service State Management](#service-state-management)

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
        PARALLEL["parallel_agent.sh"]:::process
        GIT_PLATFORM["git_platform.sh"]:::process
        GIT_OPS["git_ops.sh"]:::process
    end

    subgraph "Agent Services"
        GEMINI["Gemini CLI"]:::external
        CURSOR["Cursor Agent"]:::external
        GH["GitHub CLI (gh)"]:::external
        GLAB["GitLab CLI (glab)"]:::external
    end

    USER --> BOOTSTRAP
    BOOTSTRAP --> SERVICES
    USER --> CLAUDE_CLI
    CLAUDE_CLI --> PARALLEL
    CLAUDE_CLI --> GIT_OPS
    GIT_OPS --> GIT_PLATFORM
    GIT_PLATFORM -.->|github| GH
    GIT_PLATFORM -.->|gitlab| GLAB
    PARALLEL --> GEMINI
    PARALLEL --> CURSOR
    SERVICES -.->|config| PARALLEL
    COMMAND_CFG -.->|thresholds| PARALLEL
    VALIDATION_CFG -.->|criteria| PARALLEL
```

**Key Components**:

- **bootstrap.sh**: Automated installation and configuration deployment
- **Git Platform Scripts**: Platform-agnostic Git operations (GitHub/GitLab/plain git)
- **parallel_agent.sh**: Orchestrates multiple LLM agents for cross-verification
- **Configuration Layer**: YAML files controlling behavior and validation rules
- **Agent Services**: External LLM and Git hosting CLIs

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

    GEMINI_EXEC --> COLLECT
    CURSOR_EXEC --> COLLECT
    CLAUDE_EXEC --> COLLECT

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

## Command Processing Architecture

How slash commands are processed from user input to execution with parallel agent integration.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef external fill:#3b82f6,stroke:#1d4ed8,color:#fff

    USER["User: /command args"]:::input

    subgraph "Command Layer"
        PARSE["Parse Command & Args"]:::process
        LOAD_CMD["Load Command Definition<br/>(.md / .mdc / .toml)"]:::process
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
- **CONDITIONAL**: `/docs-diagrams` (5+ modules), `/plan-manage` (complex planning)
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
        SERVICES["services.yml<br/>(Claude, Gemini, Cursor,<br/>GitHub CLI, GitLab CLI)"]:::config
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

## Related Documents

- [AGENTS.md](../AGENTS.md) - AI agent instructions for all platforms
- [CLAUDE.md](../CLAUDE.md) - Claude Code project instructions
- [README.md](../README.md) - Project overview and quick start
- [docs/GETTING_STARTED.md](GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common problems and solutions
- [.claude/.plans/README.md](../.claude/.plans/README.md) - Plan management quick reference
