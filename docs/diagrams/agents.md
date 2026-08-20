# Agent Dispatch

> Module graph, backend selection, and the execution flow of a parallel run.

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

- **Cursor / Codex / Antigravity / Devin** have no SDK path — they always run via CLIAgent and bypass
  `select_backend()` entirely
- **All five providers** can therefore execute through CLIAgent paths; the `cli_agents:` block
  in `parallel_agent.yml` carries the per-provider argv shape (`base_args`, `model_args`,
  `prompt_args`, output strategy)
- **Degradation is per-provider**: a failed backend (exception at construction) skips just that
  provider with a warning; orchestration continues with the remaining agents subject to the
  minimum-agent check

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
        CURSOR_EXEC["Cursor Agent<br/>(cursor-grok-4.5-low/medium/high)"]:::process
        CLAUDE_EXEC["Claude — SDK or claude CLI<br/>(haiku/sonnet/opus)"]:::process
        CODEX_EXEC["Codex CLI<br/>(gpt-5.6-luna/terra/sol)"]:::process
        AGY_EXEC["Antigravity CLI<br/>(agy, gemini-3.6-flash-high)"]:::process
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

---

[← Architecture Diagrams](README.md)
