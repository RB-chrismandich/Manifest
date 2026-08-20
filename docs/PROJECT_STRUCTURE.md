# Project Structure

> Where everything lives in this repository.

## Project Structure

```text
Manifest/
├── bootstrap.sh                     # Cross-platform installation script (macOS/Linux)
├── bootstrap/                       # Modular bootstrap libraries and extension hooks
│   ├── lib/
│   │   ├── common.sh                # Shared bootstrap helpers (output, prompts, symlinks)
│   │   ├── modules.sh               # Module loader + lifecycle hook registry
│   │   ├── platform.sh              # Platform detection + timeout/browser helpers
│   │   ├── config.sh                # Arg parsing + service config read/write helpers
│   │   ├── install.sh               # CLI installation routines
│   │   ├── auth.sh                  # Authentication + state setup routines
│   │   ├── deploy.sh                # Deployment/verification/summary routines
│   │   ├── mcp.sh                   # MCP installation/configuration routines
│   │   └── skillclaw.sh             # SkillClaw ingest/evolve install/enable/disable routines
│   └── modules/README.md            # How to add custom bootstrap modules/hooks
├── CLAUDE.md                        # Claude Code project context
├── AGENTS.md                        # AI agent instructions (all platforms)
├── configs/                         # Deployment source configs (deployed to ~/ via bootstrap)
│   ├── claude/                      # → ~/.claude/ (primary configuration)
│   │   ├── CLAUDE.md                # Orchestration guide
│   │   ├── skills/                  # → ../../.apm/skills (symlink; source of truth)
│   │   ├── prompts/                 # Agent orchestration templates
│   │   ├── config/                  # YAML configuration files
│   │   │   ├── services.yml         # Agent enable/disable states
│   │   │   ├── mcp_servers.yml      # Default MCP server registry
│   │   │   ├── command_config.yml   # Tool policies, thresholds, model selection
│   │   │   ├── validation_criteria.yml # Tier 1/2 validation rules
│   │   │   ├── labels.yml           # Canonical label registry
│   │   │   └── skillclaw.yml        # SkillClaw ingest/evolve knobs + token budget config
│   │   ├── scripts/                 # Orchestration scripts
│   │   │   ├── parallel_agent.py    # Entry point shim (delegates to agents/)
│   │   │   ├── agents/              # Modular orchestration package
│   │   │   │   ├── cli.py           # Argparse + main() coroutine
│   │   │   │   ├── orchestrator.py  # Parallel execution + consensus scoring
│   │   │   │   ├── runners.py       # Agent classes (Claude/Gemini/Cursor/Codex)
│   │   │   │   ├── config.py        # Config, Logger, RateLimiter, ServiceConfig
│   │   │   │   ├── synthesis.py     # Disagreement resolution engine
│   │   │   │   └── validation.py    # Tier 1/2 validation engine
│   │   │   ├── git_platform.sh      # Git platform detection
│   │   │   ├── git_ops.sh           # Platform-agnostic Git operations
│   │   │   ├── linear_ops.sh        # Linear API wrapper (GraphQL)
│   │   │   ├── issue_support.sh     # Issue-linking engine for pr-/issue-sync-commit hooks
│   │   │   ├── issue_support_hook.sh # PostToolUse dispatcher routing PRs/commits to the engine
│   │   │   ├── install_issue_hooks.sh # Enable/remove issue-linking hooks (PostToolUse or native)
│   │   │   ├── auto_issue_dev.sh    # Selection/dependency engine for /issue-dev-auto
│   │   │   ├── sync-skills.sh       # Skill deployment to home targets
│   │   │   ├── label_sync.sh        # Label provisioning across platforms
│   │   │   ├── skillclaw_scrub.py   # Redact API keys/auth headers from captured sessions
│   │   │   ├── skillclaw_promote.py # Evolve captured sessions into candidate SKILL.md files
│   │   │   └── skillclaw_promote.sh # CLI wrapper: dry-run preview or --apply to open a PR
│   │   └── settings.local.json      # Default permissions + MCP servers
│   ├── cursor/                      # → ~/.cursor/ (Cursor IDE)
│   │   ├── rules/                   # Cursor rules (.mdc) adapted from skills
│   │   ├── mcp.json                 # Cursor MCP server defaults
│   │   └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
│   ├── gemini/                      # → ~/.gemini/ (Gemini CLI)
│   │   ├── GEMINI.md                # Orchestration guide for Gemini
│   │   ├── settings.json            # Gemini settings
│   │   └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
│   └── codex/                       # → ~/.codex/ (Codex CLI)
│       ├── AGENTS.md                # Codex guide (symlink to ../../AGENTS.md)
│       └── (symlinks to ../claude/) # scripts, config, prompts, skills, .plans
├── .claude/                         # Repo-specific config only (does NOT override sessions)
│   ├── CLAUDE.md                    # Developer guide for working in this repo
│   └── settings.local.json          # Repo-relevant permissions only
├── .apm/skills/                     # Skill source of truth (sole; retired skill supply removed 2026-07-27)
│   └── skills/                      # skill library deployed to ~/.claude/skills/ by bootstrap
├── tests/                           # Test suites
│   ├── python/                      # pytest tests for parallel_agent and agents/
│   └── bats/                        # Bats shell tests for bootstrap and scripts
└── docs/
    ├── README.md                    # Documentation hub
    ├── GETTING_STARTED.md           # First-time setup walkthrough
    ├── configuration/              # Config reference, one subject per page
    ├── diagrams/                   # Mermaid system diagrams (20, one subject per page)
    ├── SKILLCLAW.md                 # SkillClaw integration guide
    ├── troubleshooting/            # Symptom-indexed problem pages
    └── COMMANDS.md                  # Command reference
```

---

---

[← Manifest README](../README.md)
