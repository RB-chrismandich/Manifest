# Architecture Diagrams

> Visual documentation of the Manifest parallel LLM agent orchestration framework

**Last Updated**: 2026-06-15
**Project**: Manifest - AI Agent Orchestration Framework

---

## Table of Contents

1. [Application Architecture](#application-architecture)
2. [Python Parallel Agent Architecture](#python-parallel-agent-architecture)
3. [agents/ Package Module Dependency Graph](#agents-package-module-dependency-graph)
4. [Agent Backend Selection (SDK vs CLI Fallback)](#agent-backend-selection-sdk-vs-cli-fallback)
5. [Git Platform Detection & Operations](#git-platform-detection--operations)
6. [Bootstrap Installation Flow](#bootstrap-installation-flow)
7. [Parallel Agent Execution Flow](#parallel-agent-execution-flow)
8. [Skill Processing Architecture](#skill-processing-architecture)
9. [Validation Pipeline](#validation-pipeline)
10. [Model Selection & Credit Fallback](#model-selection--credit-fallback)
11. [Model Pin Staleness Check](#model-pin-staleness-check)
12. [Configuration Layer](#configuration-layer)
13. [Cross-Verification Consensus](#cross-verification-consensus)
14. [Service State Management](#service-state-management)
15. [Issue Management Architecture](#issue-management-architecture)
16. [Issue-Linking Hooks (commit-issue-sync / pr-issue-sync)](#issue-linking-hooks-commit-issue-sync--pr-issue-sync)
17. [Autonomous Issue Developer (/auto-issue-dev)](#autonomous-issue-developer-auto-issue-dev)
18. [Label Management Architecture](#label-management-architecture)
19. [SkillClaw Passive Ingest & Evolve Pipeline](#skillclaw-passive-ingest--evolve-pipeline)

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
        PARALLEL_PY["parallel_agent.py"]:::process
        AGENTS_PKG["agents/ package\n(cli · orchestrator · runners\nconfig · synthesis · validation)"]:::process
        GIT_PLATFORM["git_platform.sh"]:::process
        GIT_OPS["git_ops.sh"]:::process
    end

    subgraph "Agent Services"
        GEMINI["Gemini<br/>(SDK or gemini CLI)"]:::external
        CURSOR["Cursor Agent"]:::external
        CLAUDE_API["Claude<br/>(SDK or claude CLI)"]:::external
        CODEX["Codex CLI"]:::external
        AGY["Antigravity CLI (agy)"]:::external
        GH["GitHub CLI (gh)"]:::external
        GLAB["GitLab CLI (glab)"]:::external
    end

    subgraph "SkillClaw Subsystem"
        SKILLCLAW_INGEST["skillclaw_ingest.py\n(normalize + window/settle\n+ incremental state)"]:::process
        SKILLCLAW_SCRUB["skillclaw_scrub.py\n(secret redaction)"]:::process
        SKILLCLAW_EVOLVE["skillclaw_evolve.py\n(map-reduce via claude -p)"]:::process
        SKILLCLAW_PROMOTE["skillclaw_promote.sh\n(classify → reject-dir → PR)"]:::process
        SKILLSHARE[".skillshare/skills/\n(committed library)"]:::config
        SKILLCLAW_INGEST --> SKILLCLAW_SCRUB --> SKILLCLAW_EVOLVE --> SKILLCLAW_PROMOTE --> SKILLSHARE
    end

    USER --> BOOTSTRAP
    BOOTSTRAP --> SERVICES
    USER --> CLAUDE_CLI
    CLAUDE_CLI --> PARALLEL_PY
    PARALLEL_PY --> AGENTS_PKG
    CLAUDE_CLI --> GIT_OPS
    GIT_OPS --> GIT_PLATFORM
    GIT_PLATFORM -.->|github| GH
    GIT_PLATFORM -.->|gitlab| GLAB
    PARALLEL_PY --> GEMINI
    PARALLEL_PY --> CURSOR
    PARALLEL_PY --> CLAUDE_API
    PARALLEL_PY --> CODEX
    PARALLEL_PY --> AGY
    SERVICES -.->|config| PARALLEL_PY
    COMMAND_CFG -.->|thresholds| PARALLEL_PY
    VALIDATION_CFG -.->|criteria| PARALLEL_PY
    CLAUDE_CLI -.->|transcripts| SKILLCLAW_INGEST
```

**Key Components**:

- **bootstrap.sh**: Automated installation and configuration deployment with Python version detection
- **Git Platform Scripts**: Platform-agnostic Git operations (GitHub/GitLab/plain git)
- **parallel_agent.py**: Python orchestrator with full feature parity
  (logging, validation, synthesis, streaming, Codex agent, services.yml)
- **Configuration Layer**: YAML files controlling behavior, validation rules, and Phase 3 features
- **Agent Services**: External LLM and Git hosting CLIs. Claude and Gemini execute via their
  SDK when the package + API key are present, otherwise fall back to their OAuth-authenticated
  CLI binaries (`claude` / `gemini`) through the generic CLIAgent — all five providers can run
  through CLIAgent paths
- **SkillClaw Subsystem**: Passive transcript ingestion pipeline — reads existing Claude Code
  session `.jsonl` files, scrubs secrets, distills candidate skills via `claude -p` (Max-backed
  map-reduce), and opens a PR-gated review into `.skillshare/skills/`; no daemon, no proxy

---

## Python Parallel Agent Architecture

Architecture of the modular `agents/` package. `parallel_agent.py` is now a thin entry point;
all logic lives in six focused modules: `cli`, `orchestrator`, `runners`, `config`, `synthesis`, `validation`.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef active fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef pending fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef error fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef external fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87

    USER["User/Claude CLI"]:::external

    subgraph "agents/cli.py"
        MAIN["main()"]:::active
        SELECT["select_backend()<br/>(sdk | cli | skip)"]:::active
    end

    subgraph "agents/config.py"
        LOGGER["Logger<br/>(correlation IDs, rotation)"]:::active
        CONFIG["Config<br/>(YAML loader)"]:::config
        SVC_CFG["ServiceConfig<br/>(services.yml)"]:::config
        LIMITER["RateLimiter<br/>(token bucket)"]:::active
    end

    subgraph "agents/orchestrator.py"
        ORCH["Orchestrator"]:::active
        STREAM["Streaming Display<br/>(Rich Live)"]:::active
    end

    subgraph "agents/runners.py"
        BASE["BaseAgent<br/>(rate limiting, timeout, fallback)"]:::active
        CLAUDE_AG["ClaudeAgent<br/>(SDK, streaming support)"]:::active
        GEMINI_AG["GeminiAgent<br/>(SDK, dual package support)"]:::active
        CLI_AG["CLIAgent<br/>(claude | gemini | cursor | codex | antigravity,<br/>config-driven)"]:::active
    end

    subgraph "agents/validation.py + synthesis.py"
        VALIDATE["ValidationEngine<br/>(Tier 1 + Tier 2)"]:::active
        SYNTH["SynthesisEngine<br/>(disagreement resolution)"]:::active
    end

    subgraph "External APIs"
        ANTHROPIC["Anthropic API<br/>(Claude)"]:::external
        GOOGLE["Google Gemini API<br/>(OAuth/API key)"]:::external
        CLI_BINS["CLI binaries<br/>(claude | gemini | cursor | codex | agy)"]:::external
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
    MAIN --> SELECT
    SELECT -.->|sdk| CLAUDE_AG
    SELECT -.->|sdk| GEMINI_AG
    SELECT -.->|cli fallback| CLI_AG
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
    BASE --> CLI_AG

    CLAUDE_AG --> ANTHROPIC
    GEMINI_AG --> GOOGLE
    CLI_AG --> CLI_BINS

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
- **select_backend()**: Per-provider backend picker for SDK-capable providers (Claude, Gemini):
  SDK when package + API key are both present, else OAuth-authenticated CLI binary via CLIAgent,
  else SDK-own-auth (ADC/OAuth), else skip with a warning — never a crashed orchestration
- **CLIAgent**: Generic YAML-driven subprocess agent; provider variation (claude | gemini |
  cursor | codex | antigravity) is config data in the `cli_agents:` block — no per-provider
  subclass needed. The claude/gemini entries back the OAuth CLI fallback
- **Dual Package Support**: google-genai (new) with fallback to google-generativeai (legacy), unified interface

**Execution Flow**:

1. **Initialization**: Load config + services.yml, create logger with correlation ID, set up rate limiters
2. **Agent Selection**: services.yml state -> `--*-only` exclusive flags -> `--no-*` overrides -> minimum agent check
3. **Backend Selection**: `select_backend()` picks SDK vs CLI fallback for Claude/Gemini;
   Cursor/Codex/Antigravity always run via CLIAgent
4. **Agent Execution**: Run Claude/Gemini/Cursor/Codex/Antigravity in parallel with streaming or progress display
5. **Consensus**: Calculate consensus score using keyword-based analysis
6. **Synthesis**: If consensus < 50%, trigger SynthesisEngine for unified recommendation
7. **Validation**: Run ValidationEngine if `--validate` flag set
8. **Output**: Write structured logs, JSON results (with duration), markdown summary (sandbox-aware fallback)

**Statistics**:

- Modules: 6 (`config`, `runners`, `synthesis`, `validation`, `orchestrator`, `cli`) + `__init__`
- Classes: 11 (Config, ServiceConfig, Logger, RateLimiter, ValidationEngine, SynthesisEngine,
  BaseAgent, ClaudeAgent, GeminiAgent, CLIAgent, Orchestrator)
- CLI Flags: 28 (argparse in `agents/cli.py`)
- Agents: 5 (Claude, Gemini, Cursor, Codex, Antigravity)
- Total lines: ~2,540 across package (27-line entry point)

---

## agents/ Package Module Dependency Graph

Import dependency graph of the `agents/` package (PR #260). Arrows point from depended-upon
module to dependant — `config.py` is the shared foundation with zero local deps; `cli.py` has
the highest fan-in and wires all modules together.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef foundation fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef mid fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef top fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef entry fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e

    CONFIG["config.py\nConfig · Logger\nRateLimiter · ServiceConfig"]:::foundation

    RUNNERS["runners.py\nBaseAgent · ClaudeAgent\nGeminiAgent · CLIAgent"]:::mid

    SYNTHESIS["synthesis.py\nSynthesisEngine"]:::mid

    VALIDATION["validation.py\nValidationEngine"]:::mid

    ORCHESTRATOR["orchestrator.py\nOrchestrator"]:::top

    CLI["cli.py\nmain() · argparse"]:::top

    ENTRY["parallel_agent.py\n(entry point, 27 lines)"]:::entry

    CONFIG --> RUNNERS
    CONFIG --> SYNTHESIS
    CONFIG --> VALIDATION
    CONFIG --> ORCHESTRATOR
    RUNNERS --> ORCHESTRATOR
    SYNTHESIS --> ORCHESTRATOR
    VALIDATION --> ORCHESTRATOR
    CONFIG --> CLI
    RUNNERS --> CLI
    ORCHESTRATOR --> CLI
    CLI --> ENTRY
```

**Module responsibilities**:

| Module | Responsibility | Deps |
|--------|---------------|------|
| `config.py` | Config, Logger, RateLimiter, ServiceConfig, optional SDK guards | stdlib, yaml |
| `runners.py` | All four agent classes + BaseAgent | config |
| `synthesis.py` | SynthesisEngine — disagreement resolution | config |
| `validation.py` | ValidationEngine — Tier 1/2 criteria | config |
| `orchestrator.py` | Parallel execution, consensus scoring, Rich streaming | config, runners, synthesis, validation |
| `cli.py` | Argparse, `main()`, agent wiring | config, runners, orchestrator |
| `parallel_agent.py` | `asyncio.run(main())` entry point | cli |

**Design principle**: Dependency arrows flow strictly bottom-up. No circular imports.
`config.py` is independently testable; `orchestrator.py` is testable without `cli.py`.

---

## Agent Backend Selection (SDK vs CLI Fallback)

How `select_backend()` in `agents/cli.py` picks an execution backend for the SDK-capable
providers (Claude, Gemini). The SDK is preferred only when both the package and its API key
are present; otherwise the OAuth-authenticated provider CLI (`claude` / `gemini`) is used via
the generic CLIAgent — the common subscription-login setup needs no API key. An installed SDK
may carry its own auth (ADC/OAuth), so it is tried before the provider is skipped.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef sdk fill:#22c55e,stroke:#166534,color:#fff
    classDef cli fill:#3b82f6,stroke:#1d4ed8,color:#fff
    classDef skip fill:#ef4444,stroke:#dc2626,color:#fff

    PROVIDER["Enabled SDK-capable provider<br/>(claude | gemini)"]:::input

    SDK_KEY{"SDK package installed<br/>AND API key set?<br/>(ANTHROPIC_API_KEY /<br/>GOOGLE_API_KEY)"}:::decision
    CLI_PATH{"Provider CLI on PATH?<br/>(claude / gemini binary)"}:::decision
    SDK_ONLY{"SDK package<br/>installed?"}:::decision

    SDK_BACKEND["backend = sdk<br/>ClaudeAgent / GeminiAgent"]:::sdk
    CLI_BACKEND["backend = cli<br/>CLIAgent (OAuth-authenticated CLI,<br/>cli_agents: claude/gemini entry)"]:::cli
    SDK_OWN_AUTH["backend = sdk<br/>(SDK-own-auth: ADC/OAuth)"]:::sdk
    SKIP["Skip provider<br/>(warning, never a crash)"]:::skip

    CONSTRUCT{"Agent construction<br/>raises?<br/>(missing key, broken auth,<br/>malformed cli_agents)"}:::decision
    AGENTS["Agent joins the<br/>parallel run"]:::sdk

    PROVIDER --> SDK_KEY
    SDK_KEY -->|Yes| SDK_BACKEND
    SDK_KEY -->|No| CLI_PATH
    CLI_PATH -->|Yes| CLI_BACKEND
    CLI_PATH -->|No| SDK_ONLY
    SDK_ONLY -->|Yes| SDK_OWN_AUTH
    SDK_ONLY -->|No| SKIP

    SDK_BACKEND --> CONSTRUCT
    CLI_BACKEND --> CONSTRUCT
    SDK_OWN_AUTH --> CONSTRUCT
    CONSTRUCT -->|No| AGENTS
    CONSTRUCT -->|Yes| SKIP
```

**Key points**:

- **Cursor / Codex / Antigravity** have no SDK path — they always run via CLIAgent and bypass
  `select_backend()` entirely
- **All five providers** can therefore execute through CLIAgent paths; the `cli_agents:` block
  in `parallel_agent.yml` carries the per-provider argv shape (`base_args`, `model_args`,
  `prompt_args`, output strategy)
- **Degradation is per-provider**: a failed backend (exception at construction) skips just that
  provider with a warning; orchestration continues with the remaining agents subject to the
  minimum-agent check

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

Complete installation and configuration deployment process. Mirrors `main()` in
`bootstrap.sh` plus the routines in `bootstrap/lib/`: the services banner is printed
**after** the existing config is loaded (so displayed toggles match what deploys), and
soft-failure guards keep `set -e` from aborting the pipeline mid-flight — the full
deploy → skillclaw state → python deps → auth → verify → summary sequence always runs.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef success fill:#22c55e,stroke:#166534,color:#fff
    classDef skip fill:#e5e7eb,stroke:#6b7280,color:#374151
    classDef warning fill:#eab308,stroke:#a16207,color:#fff

    START["./bootstrap.sh"]:::input
    LOAD_LIBS["Load bootstrap/lib/*.sh<br/>+ parse CLI arguments"]:::process

    RECONFIG{"--reconfigure?"}:::decision
    RECONFIG_PATH["Reconfigure path:<br/>services.yml → skillclaw state<br/>→ python deps + browser-use"]:::process

    LOAD_CONFIG["Load existing services.yml<br/>(merge with CLI flags;<br/>explicit flags win)"]:::process
    BANNER["Show services banner<br/>(printed AFTER config load —<br/>reflects merged toggles)"]:::process
    CONFIRM{"Continue<br/>with setup?"}:::decision
    CANCELLED["Setup cancelled"]:::skip

    PLATFORM["Check platform +<br/>create ~/.manifest state dirs"]:::process

    SKIP_INSTALL{"--skip-install?"}:::decision
    INSTALLS["Install CLIs (soft-fail, counted):<br/>package manager · node · claude<br/>gemini · codex · gh · glab · jq · cursor"]:::process

    DEPLOY["deploy_configs<br/>(~/.claude primary; chmod +x<br/>scripts/*.sh AND *.py;<br/>write services.yml)"]:::process
    SKILLCLAW["skillclaw_apply_state<br/>(launchd cleanup guarded —<br/>no set -e abort)"]:::process
    PYDEPS["Install python deps<br/>+ browser-use (if enabled)"]:::process

    MCP{"--install-mcp?"}:::decision
    INSTALL_MCP["Configure MCP servers<br/>(interactive per-server)"]:::process

    SKIP_AUTH{"--skip-auth?"}:::decision
    AUTH["Auth checks (soft-fail, counted):<br/>claude · gemini · codex<br/>gh · glab · cursor info"]:::process

    VERIFY["verify_installation<br/>(errors counted, never aborts)"]:::process
    SUMMARY["print_summary<br/>(quick-start + auth guidance)"]:::process
    DONE["Installation complete"]:::success
    EXIT_WARN["Exit 1 if verification<br/>reported errors"]:::warning

    START --> LOAD_LIBS
    LOAD_LIBS --> RECONFIG
    RECONFIG -->|Yes| RECONFIG_PATH
    RECONFIG_PATH --> DONE
    RECONFIG -->|No| LOAD_CONFIG
    LOAD_CONFIG --> BANNER
    BANNER --> CONFIRM
    CONFIRM -->|No| CANCELLED
    CONFIRM -->|Yes| PLATFORM
    PLATFORM --> SKIP_INSTALL
    SKIP_INSTALL -->|No| INSTALLS
    SKIP_INSTALL -->|Yes| DEPLOY
    INSTALLS --> DEPLOY
    DEPLOY --> SKILLCLAW
    SKILLCLAW --> PYDEPS
    PYDEPS --> MCP
    MCP -->|Yes| INSTALL_MCP
    MCP -->|No| SKIP_AUTH
    INSTALL_MCP --> SKIP_AUTH
    SKIP_AUTH -->|No| AUTH
    SKIP_AUTH -->|Yes| VERIFY
    AUTH --> VERIFY
    VERIFY --> SUMMARY
    SUMMARY --> DONE
    SUMMARY -.-> EXIT_WARN
```

**Key Features**:

- **Banner after config load**: the services banner is printed only after
  `load_existing_config` merges `services.yml` with CLI flags, so the displayed toggles
  always match what will actually be deployed
- **Soft-fail install/auth/verify**: per-tool installs, auth checks, and
  `verify_installation` return error counts instead of aborting under `set -e`; the
  pipeline always reaches the summary (verification errors still exit 1 at the end)
- **Deploy chmod covers Python**: `deploy_configs` marks both `scripts/*.sh` and
  `scripts/*.py` executable
- **skillclaw_apply_state runs unconditionally after deploy**: applies enable/disable state
  and removes any legacy launchd capture daemon; the launchd cleanup is guarded so a missing
  service can no longer abort the rest of the bootstrap (python deps, auth, verify, summary)
- **Auto-Detection**: gh/glab default to `auto` mode (enable if already installed)
- **Platform-Specific Install**: Uses appropriate package manager (brew/apt/dnf/pacman)
- **Dependency Checking**: Verifies jq is installed (required for git_ops.sh JSON normalization)
- **SkillClaw (disabled by default)**: When `--enable-skillclaw` is passed, sets `chmod 700`
  on `~/.skillclaw/` and enables the passive transcript-ingestion pipeline; no proxy, no daemon,
  no supervisor required

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
        GEMINI_EXEC["Gemini — SDK or gemini CLI<br/>(gemini-3-flash-preview / 3-pro-preview)"]:::process
        CURSOR_EXEC["Cursor Agent<br/>(gpt-5.1/5.2)"]:::process
        CLAUDE_EXEC["Claude — SDK or claude CLI<br/>(haiku/sonnet/opus/fable)"]:::process
        CODEX_EXEC["Codex CLI<br/>(gpt-5.4-mini/gpt-5.4/gpt-5.5)"]:::process
        AGY_EXEC["Antigravity CLI<br/>(agy, Gemini 3.5 Flash (High))"]:::process
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
    CHECK_SERVICES --> AGY_EXEC

    GEMINI_EXEC --> COLLECT
    CURSOR_EXEC --> COLLECT
    CLAUDE_EXEC --> COLLECT
    CODEX_EXEC --> COLLECT
    AGY_EXEC --> COLLECT

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
- **Backend Selection**: Claude/Gemini run via SDK when package + API key are present,
  otherwise via their OAuth-authenticated CLI through CLIAgent (see
  [Agent Backend Selection](#agent-backend-selection-sdk-vs-cli-fallback))
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
        PARALLEL["Parallel Agent Execution<br/>(parallel_agent.py)"]:::external
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
gpt-5.2 (advanced) → gpt-5.1-codex (flash) → gpt-5.1-codex-mini (mini)
```

**Claude Fallback Chain**:

```text
fable → opus → sonnet → haiku
```

**Gemini Fallback Chain**:

```text
gemini-3-pro-preview (pro) → gemini-3-flash-preview (flash)
```

**Codex Fallback Chain**:

```text
gpt-5.5 (advanced) → gpt-5.4 (flash) → gpt-5.4-mini (mini)
```

**Error Detection**:
The script parses stderr for patterns:

- "credit", "quota", "rate limit", "insufficient"
- Automatically retries with next cheaper model
- Continues with available agents if one exhausts credits

---

## Model Pin Staleness Check

How `model_check.sh` verifies the `model_tiers` pins in `parallel_agent.yml` against live
provider listings, including the opt-in live-probe mode (`MODEL_CHECK_PROBE=1`) for
OAuth-only machines, and how `check_status.sh` reports the result honestly
(stale / unverified / verified). Warn-only: every failure degrades to SKIPPED and the
exit code is always 0.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef ok fill:#22c55e,stroke:#166534,color:#fff
    classDef warn fill:#eab308,stroke:#a16207,color:#fff
    classDef stale fill:#ef4444,stroke:#dc2626,color:#fff

    CALLER["check_status.sh /<br/>/health-check"]:::input
    MODEL_CHECK["model_check.sh<br/>(reads model_tiers pins)"]:::process

    API_KEY{"API key set?<br/>(claude / gemini)"}:::decision
    LISTING["List models via API<br/>(api.anthropic.com /<br/>generativelanguage)"]:::process
    PROBE_OPT{"MODEL_CHECK_PROBE=1<br/>and CLI installed?"}:::decision
    PROBE["Live one-shot probe per pin<br/>(claude --model X -p /<br/>gemini -m X -p)"]:::process

    AGY_LIST["antigravity: agy models<br/>listing check"]:::process
    UNSUP["cursor / codex:<br/>UNSUPPORTED<br/>(no listing command)"]:::warn

    PIN_OK["OK<br/>(pin verified)"]:::ok
    PIN_STALE["STALE<br/>(pin not served)"]:::stale
    PIN_SKIP["SKIPPED<br/>(no credentials /<br/>probe failed)"]:::warn

    AGG{"check_status.sh<br/>aggregation"}:::decision
    REPORT_STALE["⚠ N stale model pin(s) —<br/>update model_tiers"]:::stale
    REPORT_UNVER["○ N check(s) unverified —<br/>run MODEL_CHECK_PROBE=1<br/>for a live CLI probe"]:::warn
    REPORT_OK["✓ all pins verified"]:::ok

    CALLER --> MODEL_CHECK
    MODEL_CHECK --> API_KEY
    MODEL_CHECK --> AGY_LIST
    MODEL_CHECK --> UNSUP
    API_KEY -->|Yes| LISTING
    API_KEY -->|No| PROBE_OPT
    PROBE_OPT -->|Yes| PROBE
    PROBE_OPT -->|No| PIN_SKIP
    LISTING --> PIN_OK
    LISTING --> PIN_STALE
    PROBE --> PIN_OK
    PROBE --> PIN_STALE
    PROBE --> PIN_SKIP
    AGY_LIST --> PIN_OK
    AGY_LIST --> PIN_STALE

    PIN_OK --> AGG
    PIN_STALE --> AGG
    PIN_SKIP --> AGG
    AGG -->|stale > 0| REPORT_STALE
    AGG -->|skipped > 0| REPORT_UNVER
    AGG -->|all OK| REPORT_OK
```

**Check modes per provider**:

| Provider | With API key | Without API key | Notes |
|----------|--------------|-----------------|-------|
| claude | `GET /v1/models` listing | `MODEL_CHECK_PROBE=1`: one tiny `claude --model <pin> -p` call per pin; else SKIPPED | Probe needed because OAuth-only machines have no key — broken pins would otherwise read as green |
| gemini | `GET /v1beta/models` listing | `MODEL_CHECK_PROBE=1`: one tiny `gemini -m <pin> -p` call per pin; else SKIPPED | Current pins: `gemini-3-flash-preview` / `gemini-3-pro-preview` |
| antigravity | n/a | `agy models` listing (no key needed) | CLI listing only |
| cursor / codex | n/a | n/a | UNSUPPORTED — no model-listing command |

**Honest reporting** (`check_status.sh`):

- Any STALE pins → yellow warning with count (update `model_tiers`)
- Any SKIPPED checks → "unverified" line suggesting `MODEL_CHECK_PROBE=1 model_check.sh`;
  the green "all pins verified" line never overclaims what was actually checked
- All OK → green "Model pin check complete — all pins verified"

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
        SERVICES["services.yml<br/>(Claude, Gemini, Cursor, Codex,<br/>GitHub CLI, GitLab CLI, SkillClaw)"]:::config
        COMMAND_CFG["command_config.yml<br/>(Thresholds, Tool Policies,<br/>Model Selection)"]:::config
        VALIDATION["validation_criteria.yml<br/>(Tier 1/2 Criteria,<br/>Command Overrides)"]:::config
        SKILLCLAW_CFG["skillclaw.yml<br/>(storage root, window_days,<br/>settle_minutes, token_budget,<br/>evolve provider, promotion branch/labels)"]:::config
    end

    PARSE_SERVICES["Parse Service Toggles<br/>(awk parser)"]:::process
    PARSE_COMMAND["Load Command Config<br/>(YAML parser)"]:::process
    PARSE_VALID["Load Validation Rules<br/>(YAML parser)"]:::process
    PARSE_SC["Load SkillClaw Config<br/>(python3 + yaml)"]:::process

    PARALLEL["parallel_agent.py"]:::process
    COMMANDS["Command Execution"]:::process
    VALIDATORS["Validation Agents"]:::process
    SKILLCLAW_RUNTIME["skillclaw_promote.sh\nskillclaw_scrub.py\nskillclaw setup"]:::process

    BOOTSTRAP --> SERVICES
    BOOTSTRAP --> SKILLCLAW_CFG
    SERVICES --> PARSE_SERVICES
    PARSE_SERVICES --> PARALLEL

    COMMAND_CFG --> PARSE_COMMAND
    PARSE_COMMAND --> PARALLEL
    PARSE_COMMAND --> COMMANDS

    VALIDATION --> PARSE_VALID
    PARSE_VALID --> VALIDATORS
    PARSE_VALID --> PARALLEL

    SKILLCLAW_CFG --> PARSE_SC
    PARSE_SC --> SKILLCLAW_RUNTIME

    PARALLEL --> RESULT["Agent Outputs"]:::output
    COMMANDS --> RESULT
    VALIDATORS --> RESULT
    SKILLCLAW_RUNTIME --> RESULT
```

**services.yml Structure** (SkillClaw entry):

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
  skillclaw:
    enabled: false       # opt-in; enable with --enable-skillclaw
    command: skillclaw
    storage: ~/.skillclaw
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

- **Service Toggles**: Enable/disable agents and Git CLIs (including SkillClaw)
- **Auto-Detection**: gh/glab default to `auto` (enable if installed)
- **Nested Configuration**: git_cli section contains github/gitlab subsections
- **Reconfigurable**: `bootstrap.sh --reconfigure` updates toggles without reinstall
- **skillclaw.yml**: Controls `~/.skillclaw` storage layout, ingest knobs (`window_days`,
  `settle_minutes`, `max_tool_output_chars`), evolve knobs (`token_budget`, `claude -p`
  Max-backed runner), and PR promotion settings (branch prefix, base branch, labels)

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

Given 3 of 5 agents with these findings (Gemini, Cursor, Claude shown for brevity):

- **Gemini**: [A, B, C, D]
- **Cursor**: [A, B, E]
- **Claude**: [A, C, F]

**Analysis**:

- Total unique findings: A, B, C, D, E, F = **6**
- Agreements (2+ agents):
  - A: all 3 agents shown ✓
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

## Issue-Linking Hooks (commit-issue-sync / pr-issue-sync)

How the issue-linking hooks keep the GitHub/GitLab issue tracker in sync as commits
land and PRs/MRs open. A single PostToolUse dispatcher (`issue_support_hook.sh`)
classifies the Bash command that just ran and, only on success, routes to the shared
engine (`issue_support.sh`). The engine is **fail-open**: `sync-pr`/`sync-commit`
always exit 0 (bounded by a per-hook `run_with_timeout`), so a git action is never
blocked. An optional native `git post-commit` hook covers commits made outside an
AI tool.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef platform fill:#3b82f6,stroke:#1d4ed8,color:#fff
    classDef skip fill:#e5e7eb,stroke:#6b7280,color:#374151

    INSTALL["install_issue_hooks.sh --enable [--native]<br/>flips tool_policies gate +<br/>writes PostToolUse entry"]:::config

    subgraph "Triggers"
        TOOLUSE["PostToolUse payload (stdin JSON)<br/>after a Bash command"]:::input
        NATIVE["git post-commit hook<br/>(--native, non-AI commits)"]:::input
    end

    HOOK["issue_support_hook.sh<br/>classify command + success"]:::process
    CLASS{"Command class?<br/>(gh/glab/git_ops pr-create<br/>· git commit · none)"}:::decision
    OK{"Tool succeeded?<br/>(is_error / error)"}:::decision

    ENGINE["issue_support.sh<br/>sync-pr N / sync-commit HEAD<br/>(run_with_timeout, fail-open exit 0)"]:::process
    GATE{"tool_policies gate<br/>enabled?"}:::decision

    RESOLVE["resolve_candidates()<br/>branch-prefix · PR/MR body<br/>· commit-message #N refs"]:::process
    OFFER["offer_create()<br/>(no ref → dedup search,<br/>interactive create 'planned')"]:::process

    subgraph "process_issue (per linked #N)"
        TRANSITION["transition_issue<br/>forward-only label advance<br/>planned→in-progress→needs-review"]:::process
        BACKLINK["comment_backlink<br/>(idempotent marker)"]:::process
        CLOSEKW["ensure_closing_keyword<br/>Closes #N (PR only)"]:::process
    end

    GIT_OPS["git_ops.sh → gh / glab"]:::platform
    NOOP["exit 0 (no-op)"]:::skip

    INSTALL -.->|registers| TOOLUSE
    INSTALL -.->|installs| NATIVE
    TOOLUSE --> HOOK
    NATIVE --> ENGINE
    HOOK --> OK
    OK -->|No| NOOP
    OK -->|Yes| CLASS
    CLASS -->|pr| ENGINE
    CLASS -->|commit| ENGINE
    CLASS -->|none| NOOP
    ENGINE --> GATE
    GATE -->|No| NOOP
    GATE -->|Yes| RESOLVE
    RESOLVE -->|refs found| TRANSITION
    RESOLVE -->|none| OFFER
    OFFER --> TRANSITION
    TRANSITION --> BACKLINK --> CLOSEKW
    TRANSITION --> GIT_OPS
    BACKLINK --> GIT_OPS
    CLOSEKW --> GIT_OPS
```

**Trigger → target mapping**:

| Trigger | Hook class | Engine call | Status target | Extra action |
|---------|-----------|-------------|---------------|--------------|
| PR/MR created (`gh`/`glab`/`git_ops.sh pr-create`) | `pr` | `sync-pr N` | `needs-review` | back-link comment + ensure `Closes #N` |
| `git commit` / `git_ops.sh commit` | `commit` | `sync-commit HEAD` | `in-progress` | back-link comment (only advances issues already `planned`) |
| any other Bash command | `none` | — | — | no-op (exit 0) |

**Key properties**:

- **Opt-in & reversible**: `install_issue_hooks.sh --enable/--remove` flips the
  `tool_policies.{pr-issue-sync,commit-issue-sync}.enabled` gate and idempotently
  adds/removes the PostToolUse entry in `~/.claude/settings.json`. `--native` adds a
  guarded `git post-commit` hook (refuses to clobber a pre-existing one).
- **Fail-open**: `sync-pr`/`sync-commit` always exit 0; an internal `__inner`
  re-exec is bounded by `hook_timeout_seconds` (default 5s) so a slow tracker
  degrades to a warning — a re-run heals it (FR-017).
- **Idempotent**: comment back-links carry a `<!-- issue-support:sync v1 ... -->`
  marker; `Closes #N` and label transitions are skipped when already satisfied.
- **Forward-only lifecycle**: `planned → in-progress → needs-review → done` — a
  transition never moves an issue backward (rank check in `transition_issue`).
- **Issue resolution**: a linked issue is found from the branch numeric prefix
  (`017-foo` → `#17`), `#N` refs in the PR/MR body, and commit-message references.

---

## Autonomous Issue Developer (/auto-issue-dev)

How `/auto-issue-dev` (engine: `auto_issue_dev.sh`) develops **exactly one** opted-in
issue per invocation and opens a PR for review — never merging. `/loop` re-runs the
skill with fresh context for the next issue. Selection is opt-in (the `auto-dev`
label) and dependency-aware: issues with unmet `depends on #N` / `blocked by #N`
references are tagged `blocked-dependency` and skipped. Status sync and `Closes #N`
are delegated to the issue-linking hooks (above).

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TD
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef success fill:#22c55e,stroke:#166534,color:#fff
    classDef warning fill:#eab308,stroke:#a16207,color:#fff
    classDef stop fill:#e5e7eb,stroke:#6b7280,color:#374151

    LOOP["/loop /auto-issue-dev<br/>(fresh context per run)"]:::input
    PREFLIGHT["Preflight:<br/>install_issue_hooks.sh --enable<br/>+ gh/glab auth check"]:::process

    NEXT["auto_issue_dev.sh next-issue --json<br/>list 'auto-dev' open issues,<br/>drop 'blocked-dependency',<br/>oldest-first"]:::process
    DEPCHECK{"check-deps:<br/>unmet #N refs?"}:::decision
    MARK_DEP["mark-dependency<br/>add 'blocked-dependency' label<br/>+ deduped comment, skip"]:::warning

    READY{"Ready issue<br/>found?"}:::decision
    STOP_EMPTY["Exit 3 → announce<br/>'queue empty', STOP"]:::stop

    BRANCH["git switch -c N-slug<br/>(numeric prefix links #N)"]:::process
    TDD["test-driven-development:<br/>failing test → implement → green"]:::process
    VERIFY{"/verify<br/>tests + security pass?"}:::decision

    PR["git_ops.sh pr-create<br/>→ PR hook injects Closes #N,<br/>moves #N to needs-review"]:::success
    DRAFT["pr-create --draft [WIP]<br/>+ mark-blocked (needs-human label)"]:::warning
    SUMMARY["Print one-line summary;<br/>STOP (one issue per run)"]:::stop

    LOOP --> PREFLIGHT --> NEXT
    NEXT --> READY
    READY -->|No| STOP_EMPTY
    READY -->|candidate| DEPCHECK
    DEPCHECK -->|unmet| MARK_DEP
    MARK_DEP --> NEXT
    DEPCHECK -->|all met| BRANCH
    BRANCH --> TDD --> VERIFY
    VERIFY -->|Yes| PR
    VERIFY -->|No / stuck| DRAFT
    PR --> SUMMARY
    DRAFT --> SUMMARY
```

**Engine subcommands** (`auto_issue_dev.sh`, wraps `git_ops.sh`):

| Subcommand | Behavior | Exit |
|------------|----------|------|
| `next-issue [--json]` | First READY `auto-dev` issue (oldest-first, deps met) | `0` ready / `3` none |
| `check-deps <N> [--json]` | Parse `depends on / blocked by / requires / needs #N`; verify each ref is closed/merged | `0` ready / `2` unmet / `1` missing |
| `mark-blocked <N> <reason>` | Add `needs-human` label + deduped comment (fail-open) | `0` |
| `mark-dependency <N> <refs>` | Add `blocked-dependency` label + deduped comment (fail-open) | `0` |

**Invariants**:

- **Never merges** — stops at PR-open; a human reviews and merges.
- **One issue per invocation** — the loop lives in `/loop`, not inside the skill.
- **Opt-in only** — issues without the `auto-dev` label are never touched.
- **On failure** — push WIP, open a **draft** PR (no `Closes`), and `mark-blocked`
  so a human inspects partial work; if there are no commits, skip the draft.
- **Status hand-off** — `planned → in-progress → needs-review` and `Closes #N` are
  applied by the issue-linking hooks, not by this engine (see previous section).

**Labels** (`labels.yml`): `auto-dev` (opt-in selection), `blocked-dependency`
(unmet dependency, excluded until the blocker merges), `needs-human` (auto-dev
could not complete; needs a human).

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

**Canonical Labels** (3 platforms):

| Label | Color | Platforms | Used By |
|-------|-------|-----------|---------|
| `planned` | `#1D76DB` (Blue) | GitHub, GitLab, Linear | /plan-manage create |
| `in-progress` | `#FBCA04` (Yellow) | GitHub, GitLab, Linear | /plan-manage execute, commit-issue-sync |
| `needs-review` | `#E3A21A` (Orange) | GitHub, GitLab, Linear | /issue-triage, pr-issue-sync |
| `done` | `#0E8A16` (Green) | GitHub, GitLab, Linear | /plan-manage execute |
| `follow-up` | `#D4C5F9` (Lavender) | GitHub, GitLab, Linear | /issue-triage |
| `future` | `#C2E0C6` (Green) | GitHub, GitLab, Linear | /issue-prioritize |
| `auto-dev` | (opt-in) | GitHub, GitLab, Linear | /auto-issue-dev (selection) |
| `needs-human` | (flag) | GitHub, GitLab, Linear | /auto-issue-dev (mark-blocked) |
| `blocked-dependency` | (flag) | GitHub, GitLab, Linear | /auto-issue-dev (mark-dependency) |

**Deprecated**: `processed` (replaced by `done`)

**Sync Modes**:

- `--dry-run`: Report what would be created without making changes
- `--validate`: Alias for `--dry-run` (validation only)
- `--platform <name>`: Restrict sync to a single platform (github, gitlab, linear)

---

## SkillClaw Passive Ingest & Evolve Pipeline

How existing Claude Code session transcripts are passively read, scrubbed for secrets,
distilled into candidate skills, and promoted to the committed library via a PR-gated review.
No proxy, no socket, no daemon — works with Claude Max out of the box.

```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart LR
    classDef input fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    classDef process fill:#f0fdf4,stroke:#16a34a,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef secure fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    classDef config fill:#f3e8ff,stroke:#9333ea,color:#581c87
    classDef output fill:#22c55e,stroke:#166534,color:#fff

    TRANSCRIPTS["~/.claude/projects/**/*.jsonl\n(Claude Code session transcripts\nalready on disk)"]:::input

    INGEST["skillclaw_ingest.py\nnormalize turns\nstrip tool-output noise\nwindow=30d / settle=5m\nincremental state file"]:::process

    SCRUB["skillclaw_scrub.py\nRedact API keys,\nauth headers, tokens"]:::secure

    EVOLVE["skillclaw_evolve.py\nmap-reduce via claude -p\n(Max-backed)\nchunks ≤ 100 000 tokens"]:::process

    EVOLVED_LIB["~/.skillclaw/skills/\n(evolved candidates)"]:::process

    CLASSIFY["skillclaw_promote.py\nClassify NEW / CHANGED\nDrop invalid frontmatter\nCopy rejected → rejected/"]:::decision

    PROMOTE["skillclaw_promote.sh\nPR-gate: one open\nskillclaw/evolve-* PR\nat a time"]:::process

    GIT_BRANCH["git switch -c\nskillclaw/evolve-N-SHA"]:::process
    PR["git_ops.sh pr-create\n(needs-review + follow-up labels)"]:::process

    SKILLSHARE[".skillshare/skills/\n(committed library)"]:::output

    TRANSCRIPTS --> INGEST
    INGEST --> SCRUB
    SCRUB --> EVOLVE
    EVOLVE --> EVOLVED_LIB
    EVOLVED_LIB --> CLASSIFY
    CLASSIFY -->|accepted| PROMOTE
    CLASSIFY -->|rejected| EVOLVED_LIB
    PROMOTE --> GIT_BRANCH
    GIT_BRANCH --> PR
    PR --> SKILLSHARE
```

**Pipeline Stages**:

| Stage | Component | Description |
|-------|-----------|-------------|
| Source | `~/.claude/projects/**/*.jsonl` | Claude Code writes session transcripts to disk automatically; SkillClaw reads them passively |
| Ingest | `skillclaw_ingest.py` | Normalizes turns, strips tool-output noise (`max_tool_output_chars=500`), applies `window_days=30` + `settle_minutes=5` filters, tracks processed files via incremental state |
| Scrub | `skillclaw_scrub.py` | Redacts `sk-ant-*`, `sk-proj-*`, bearer tokens, `x-api-key` headers before evolve/promote |
| Evolve | `skillclaw_evolve.py` | Map-reduce via headless `claude -p` (Max-backed); greedily packs sessions into chunks under `token_budget=100 000`; reduce deduplicates by skill name |
| Classify | `skillclaw_promote.py` | Compares evolved `~/.skillclaw/skills/` against committed library; emits NEW / CHANGED / UNCHANGED; drops skills with missing or malformed frontmatter; copies rejected candidates to `~/.skillclaw/skills/rejected/` |
| Promote | `skillclaw_promote.sh` | Idempotency check (one open `skillclaw/evolve-*` PR at a time); one commit per skill; opens review PR via `git_ops.sh` |
| Review | GitHub/GitLab PR | Human review gate; each skill is an independent commit — revert to drop; merge deploys via `bootstrap.sh` skill sync |

**Key new skills**:

- `/skill-evolve` — Preview or open a review PR for SkillClaw-evolved skills
  (`skillclaw_promote.sh --apply`); dry-run by default
- `/pass-cli` — Retrieve secrets from Proton Pass via `pass-cli` agent CLI;
  handles session setup, vault/item discovery, and auto-recovery

---

## Related Documents

- [AGENTS.md](../AGENTS.md) - AI agent instructions for all platforms
- [CLAUDE.md](../CLAUDE.md) - Claude Code project instructions
- [README.md](../README.md) - Project overview and quick start
- [docs/GETTING_STARTED.md](GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](CONFIGURATION.md) - Complete configuration reference
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common problems and solutions
- [configs/claude/.plans/README.md](../configs/claude/.plans/README.md) - Plan management quick reference
