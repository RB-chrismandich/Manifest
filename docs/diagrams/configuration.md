# Configuration & Labels

> Config layering, service state, and the label registry.

**Last Updated**: 2026-08-20

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
    command: cursor-agent
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
        HEALTH["/env-check<br/>label validation"]:::script
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
| `in-progress` | `#FBCA04` (Yellow) | GitHub, GitLab, Linear | /plan-manage execute, issue-sync-commit |
| `needs-review` | `#E3A21A` (Orange) | GitHub, GitLab, Linear | /issue-triage, issue-sync-pr |
| `done` | `#0E8A16` (Green) | GitHub, GitLab, Linear | /plan-manage execute |
| `follow-up` | `#D4C5F9` (Lavender) | GitHub, GitLab, Linear | /issue-triage |
| `future` | `#C2E0C6` (Green) | GitHub, GitLab, Linear | /issue-prioritize |
| `auto-dev` | `#5319E7` (Purple) | GitHub, GitLab, Linear | /issue-dev-auto (selection) |
| `needs-human` | `#B60205` (Red) | GitHub, GitLab, Linear | /issue-dev-auto (mark-blocked) |
| `blocked-dependency` | `#6A737D` (Gray) | GitHub, GitLab, Linear | /issue-dev-auto (mark-dependency) |

**Deprecated**: `processed` (replaced by `done`)

**Sync Modes**:

- `--dry-run`: Report what would be created without making changes
- `--validate`: Alias for `--dry-run` (validation only)
- `--platform <name>`: Restrict sync to a single platform (github, gitlab, linear)

---

---

[← Architecture Diagrams](README.md)
