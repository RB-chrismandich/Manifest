# AGENTS.md

> Repository context and guidance for AI coding agents (Cursor, Claude Code, Gemini, Codex, etc.)

**Last Updated**: 2026-06-10
**Audience**: AI assistants (Cursor Agent, Claude Code, Gemini CLI, Codex CLI), contributors
**Purpose**: Provide AI agents with repository structure, deployment process, and testing guidelines

---

This file provides guidance to AI coding agents when working with code in this repository.
It follows the [AGENTS.md standard](https://agents.md/) for unified coding agent instructions.

## Token Economy (always on)

Apply at all times, in every session:

- Lead with the result. No filler ("Sure", "Here's the…"), no closing summaries.
- Match response length to the task; don't re-explain code you just wrote unless asked.
- Use programmatic edit tools for targeted edits; never reprint a whole file for a small change.
- If an implementation detail is genuinely ambiguous, ask ONE targeted question instead of guessing.
- Read what a change depends on (types, signatures, callers); skip speculative
  whole-tree crawls and re-reads of unchanged files. Don't starve context —
  a wrong edit costs more than one extra dependency read.

## MCP Default Policy

Default MCP/tool routing — use the matching tool when the task domain matches:

- **Context7 MCP** — library/API docs, code generation, setup, configuration
- **Sentry MCP** — production/runtime errors, stack traces, release regressions
- **Linear MCP** — issue requirements, acceptance criteria, project planning
- **Semgrep CLI** (`semgrep scan`) — local SAST, vulnerability and secrets
  checks (install: `brew install semgrep`)
- **DeepWiki MCP** — unfamiliar repos, dependency internals, upstream API contracts
- **Glean MCP** — internal team knowledge, runbooks, ADRs
- **Google Dev Docs MCP** — Firebase/Cloud/Android/Maps documentation
- **Atlassian MCP** — Jira issues, Confluence pages, Compass components
- **Apify MCP** — web scraping/crawling for structured external data
- **OpenTofu MCP** — Terraform/OpenTofu registry, provider/module docs

## Repository Purpose

This repository manages AI agent configurations for deployment to `~/.claude/` (and mirrored
to `~/.cursor/`, `~/.gemini/`, `~/.codex/`, and `~/.antigravity/`) on target machines. It contains
orchestration guides, skills, prompts, and scripts that enable parallel LLM agent coordination
(Cursor, Gemini CLI, Claude CLI, Codex CLI, Antigravity).

## Repository Structure

```text
configs/                             # Deployment source configs (deployed to ~/ via bootstrap.sh)
├── claude/                          # → ~/.claude/ (primary configuration)
│   ├── CLAUDE.md                    # Orchestration guide
│   ├── skills/                      # → ../../.skillshare/skills (symlink; source of truth)
│   ├── prompts/                     # Agent orchestration prompt templates
│   ├── config/                      # YAML configuration files
│   │   └── mcp_servers.yml          # Default MCP server registry (OAuth-capable)
│   ├── .plans/                      # Plan management (template, archive, abandoned)
│   ├── settings.local.json          # Default permissions and MCP server config
│   └── scripts/parallel_agent.py    # Main parallel agent orchestration script
├── cursor/                          # → ~/.cursor/ (Cursor IDE configuration)
│   ├── rules/                       # Cursor rules (.mdc) — auto-generated from SKILL.md
│   ├── mcp.json                     # Cursor MCP server defaults
│   ├── scripts -> ../claude/scripts # Symlink to shared scripts
│   ├── config -> ../claude/config   # Symlink to shared configs
│   ├── prompts -> ../claude/prompts # Symlink to shared prompts
│   └── .plans -> ../claude/.plans   # Symlink to shared plans
├── gemini/                          # → ~/.gemini/ (Gemini CLI configuration)
│   ├── GEMINI.md                    # Orchestration guide for Gemini CLI
│   ├── settings.json                # Gemini settings (includes MCP server defaults)
│   ├── scripts -> ../claude/scripts # Symlink to shared scripts
│   ├── config -> ../claude/config   # Symlink to shared configs
│   ├── prompts -> ../claude/prompts # Symlink to shared prompts
│   └── .plans -> ../claude/.plans   # Symlink to shared plans
├── codex/                           # → ~/.codex/ (Codex CLI configuration)
│   ├── AGENTS.md -> ../../AGENTS.md # Codex guide (repo-level instructions)
│   ├── scripts -> ../claude/scripts # Symlink to shared scripts
│   ├── config -> ../claude/config   # Symlink to shared configs
│   ├── prompts -> ../claude/prompts # Symlink to shared prompts
│   └── .plans -> ../claude/.plans   # Symlink to shared plans
└── antigravity/                     # → ~/.antigravity/ (Antigravity IDE)
    └── (symlinks to ../claude/)     # scripts, config, prompts, skills, .plans

.claude/                             # Repo-specific config (minimal — does NOT override sessions)
├── CLAUDE.md                        # Developer guide for working in this repo
└── settings.local.json              # Repo-relevant permissions only

templates/                           # Project scaffolding templates
├── scaffold/
│   ├── python/                      # pyproject.toml, .pre-commit-config.yaml
│   ├── go/                          # go.mod, Makefile, .golangci.yml
│   ├── node/                        # package.json, tsconfig.json, eslint.config.js
│   └── terraform/                   # main.tf, versions.tf, .tflint.hcl

bootstrap.sh                         # macOS/Linux bootstrap script
bootstrap/                           # Modular bootstrap libraries + hookable modules
├── lib/                             # Shared bootstrap logic split by concern
│   ├── common.sh                    # Shared output/prompts/symlink helpers
│   ├── modules.sh                   # Hook registry + module loader
│   ├── platform.sh                  # Platform detection + timeout/browser helpers
│   ├── config.sh                    # Argument parsing + services config helpers
│   ├── install.sh                   # CLI install routines
│   ├── auth.sh                      # Authentication + state setup routines
│   ├── deploy.sh                    # Deploy/verify/summary routines
│   └── mcp.sh                       # MCP configuration/install routines
└── modules/README.md                # How to add custom bootstrap extensions
AGENTS.md                            # This file (AI agent instructions)
CLAUDE.md                            # Claude Code-specific project instructions
```

## Bootstrap (macOS / Linux)

The `bootstrap.sh` script automates installation, deployment, and authentication.

**Supported platforms:**

- macOS (Intel and Apple Silicon)
- Linux (Debian/Ubuntu, RHEL/Fedora, Arch, openSUSE)

### Quick Start

```bash
# Full setup with all services
./bootstrap.sh

# Setup with specific services disabled
./bootstrap.sh --disable-cursor
./bootstrap.sh --disable-gemini --disable-cursor

# Skip interactive prompts
./bootstrap.sh --skip-auth --force

# Configure MCP servers (interactive per-server selection)
./bootstrap.sh --install-mcp
```

### Service Toggles

```bash
--enable-claude / --disable-claude   # Claude CLI (default: enabled)
--enable-gemini / --disable-gemini   # Gemini CLI (default: enabled)
--enable-cursor / --disable-cursor   # Cursor agent (default: enabled)
--enable-codex / --disable-codex     # Codex CLI (default: enabled)
--enable-gh / --disable-gh           # GitHub CLI (default: auto-detect)
--enable-glab / --disable-glab       # GitLab CLI (default: auto-detect)
--install-mcp                        # Configure MCP servers (interactive per-server selection)
```

## Manual Deployment

If not using bootstrap.sh, copy the configuration directories manually:

```bash
# Deploy Claude Code configuration
cp -r configs/claude/* ~/.claude/
cp -r configs/claude/.[!.]* ~/.claude/ 2>/dev/null || true
chmod +x ~/.claude/scripts/*.sh ~/.claude/scripts/parallel_agent.py

# Other platforms (Cursor/Gemini/Codex/Antigravity): copy the platform guide +
# settings, then symlink scripts/config/prompts/.plans/skills from ~/.claude/.
# See CLAUDE.md "Manual Deployment" for the full per-platform commands.
```

Required CLI tools (install those you want to use):

- `claude` - `npm install -g @anthropic-ai/claude-code`
- `gemini` - `npm install -g @google/gemini-cli`
- `cursor-agent` - `curl https://cursor.com/install -fsS | bash`
- `codex` - `npm install -g @openai/codex`

## Key Files

| File | Purpose |
|------|---------|
| `configs/claude/CLAUDE.md` | Main orchestration guide for Claude Code |
| `configs/cursor/rules/orchestration.mdc` | Main orchestration guide for Cursor (always-on rule) |
| `configs/gemini/GEMINI.md` | Main orchestration guide for Gemini CLI |
| `configs/codex/AGENTS.md` | Main orchestration guide for Codex CLI |
| `configs/claude/scripts/parallel_agent.py` | Python script that runs agents in parallel with consensus scoring |
| `configs/claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `configs/claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |

## Available Skills

All agents share the same skill library from `.skillshare/skills/` (70+ skills;
exposed via the `configs/claude/skills/` symlink).
Skills are invoked as slash commands (e.g., `/refactor-python src/`).

### Skill Reference

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/docs-readme` | Improve README documentation | NO |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/docs-all` | Run docs-readme/docs-diagrams/docs-improve as sub-agents in one pass | CONDITIONAL |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/refactor-node` | Node.js/TypeScript codebase security and quality analysis | ALWAYS |
| `/refactor-go` | Go codebase security and quality analysis | ALWAYS |
| `/refactor-terraform` | Terraform/OpenTofu IaC security, modularity, and quality analysis | ALWAYS |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact/urgency/readiness/risk | CONDITIONAL |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/browser-test` | AI-powered E2E browser testing via browser-use YAML test prompts | CONDITIONAL |
| `/checkpoint` | Create compact checkpoint summary when context is high | NO |
| `/health-check` | Verify CLI tools, auth, config syntax, MCP, symlinks | NO |
| `/sync-configs` | Detect cross-platform config drift and broken symlinks | NO |
| `/version-pin` | Enforce specific, hashed version pins in dependency files (auto-fix on demand; warn-only save hook) | ALWAYS (Tier 1) |
| `/pr-review` | Review all open PRs and recommend a disposition per PR (analysis-only) | NO |
| `/branch-clean` | Prune merged/gone/stale branches safely (dry-run by default, local-only) | CONDITIONAL (--apply) |
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run by default); requires SkillClaw enabled | NO |
| `/pass-cli` | Retrieve credentials from Proton Pass vaults via `pass-cli` agent CLI | NO |
| `/spec-review` | Independent Antigravity (agy) cross-reference of spec/plan/tasks for internal consistency; on-demand or via fail-open PostToolUse save hook (content-hash debounced, detached); analysis-only; works with speckit and superpowers layouts; silent-mode findings land in `.spec-review/feedback.md` | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect recurring antipatterns from lint, test, and review feedback | NO |
| `/ci-setup` | Configure CI/CD pipelines for a target repository (GitHub Actions or GitLab CI) | NO |
| `/code-quality` | Auto-triggered security and quality checks | AUTO (always when triggered) |
| `/dashboard` | Visualize agent efficiency metrics | NO |
| `/learning-loop` | Capture structured lessons learned | NO |
| `/performance-check` | Frontend performance audit: bundle size, Core Web Vitals, caching | NO |
| `/scaffold` | Initialize new projects with quality gates and Manifest integration | NO |
| `/ux-review` | UX audit: accessibility, responsive design, performance budgets | NO |
| `/verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |

**CLI tool** (installed to `~/.local/bin/`): `sync-skills` — sync `.skillshare/skills/`
to all home targets (daily skill dev workflow).

### Cursor Rules

All Cursor rules are auto-generated from SKILL.md files using `generate_cursor_rules.sh`.
Each skill produces a corresponding `.mdc` rule in `configs/cursor/rules/`.

| Rule | Description |
|------|-------------|
| `orchestration` | Parallel agent orchestration guide (always-on) |
| `a11y-audit` | WCAG 2.2 AA accessibility audit |
| `antipattern-detect` | Codebase antipattern detection |
| `checkpoint` | Context checkpoint |
| `ci-setup` | CI/CD pipeline configuration |
| `code-quality` | Auto-triggered security/quality checks |
| `dashboard` | Efficiency metrics |
| `docs-diagrams` | Mermaid diagram generation |
| `docs-improve` | Diataxis documentation |
| `docs-readme` | README improvement |
| `health-check` | Environment health check |
| `issue-prioritize` | Issue prioritization |
| `issue-triage` | Linear issue triage |
| `learning-loop` | Lessons learned capture |
| `performance-check` | Performance analysis |
| `plan-manage` | Plan lifecycle |
| `project-commit` | Commit pipeline |
| `refactor-go` | Go analysis |
| `refactor-node` | Node.js/TypeScript analysis |
| `refactor-python` | Python analysis |
| `refactor-shell` | Shell analysis |
| `refactor-terraform` | Terraform IaC analysis |
| `scaffold` | Project scaffolding |
| `sync-configs` | Config drift detection |
| `ux-review` | UX/accessibility audit |
| `verify` | Linter/test/security scan runner |

### Platform-Specific Notes

Skills are shared across all platforms via symlinks from `configs/claude/skills/`:

- **Claude Code**: Skills loaded from `~/.claude/skills/`
- **Cursor**: Rules auto-generated from skills into `~/.cursor/rules/` (`.mdc` files)
- **Gemini CLI**: Skills loaded from `~/.gemini/skills/` (symlink to `~/.claude/skills/`)
- **Codex CLI**: Skills loaded from `~/.codex/skills/` (symlink to `~/.claude/skills/`)
- **Antigravity**: Skills loaded from `~/.antigravity/skills/` (symlink to `~/.claude/skills/`)

## Parallel Agent Orchestration

All agents share the same orchestration script at `configs/claude/scripts/parallel_agent.py`.

```bash
# Basic code review (all 5 agents)
~/.claude/scripts/parallel_agent.py --json --timeout 600 --review /absolute/path/to/file

# Security analysis with maximum capability models
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 900 \
  --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file
```

### Validation

- **Tier 1 (blocking)**: cross-verification, security, error handling, breaking
  changes. **Tier 2 (advisory)**: bugs, performance, maintainability, tests.
- Authoritative weights: `configs/claude/config/validation_criteria.yml`.
  Consensus thresholds and verdict rules (`APPROVED`/`NEEDS_REVIEW`/`BLOCKED`):
  `configs/claude/references/orchestration.md`.

## Testing Changes

```bash
# Test parallel agent script
configs/claude/scripts/parallel_agent.py --json "Test prompt"

# Test specific mode
configs/claude/scripts/parallel_agent.py --json --review /path/to/file

# Validate YAML configs
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Plan Management

Implementation plans are tracked in `configs/claude/.plans/` (symlinked at `configs/cursor/.plans/`,
`configs/gemini/.plans/`, and `configs/codex/.plans/`) as date-prefixed markdown files (`YYYYMMDD-description.md`).

Lifecycle: `CREATE -> ACTIVE -> COMPLETED (.archive/) or ABANDONED (.abandoned/)`

## Adding New Configuration

### Adding a Claude Code Skill

1. Create a `SKILL.md` file in `.skillshare/skills/my-skill/` (the source of
   truth; `configs/claude/skills/` is a compat symlink to it)
2. Add tool policies to `configs/claude/config/command_config.yml`
3. Skills are automatically available in Claude Code after deploying via bootstrap

### Adding a Cursor Rule

1. Create an `.mdc` file in `configs/cursor/rules/` (e.g., `my-rule.mdc`)
2. Add YAML frontmatter with `description`, `globs`, and `alwaysApply`
3. Rule auto-attaches when files matching `globs` are referenced (after deploying)

### Adding a Gemini CLI Skill

Gemini CLI uses the shared skills from `configs/claude/skills/` (symlinked at `~/.gemini/skills`).
To add a new skill, follow the Claude Code skill instructions above.

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [CLAUDE.md](CLAUDE.md) - Claude Code-specific project instructions
- [docs/README.md](docs/README.md) - Documentation hub
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - First-time setup walkthrough
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration reference
- [docs/ARCHITECTURE_DIAGRAMS.md](docs/ARCHITECTURE_DIAGRAMS.md) - Visual system documentation
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plan management quick reference

## Workflow Reminders (Codex / Antigravity standing-line fallback)

Codex and Antigravity have no event-hook substrate, so the per-moment hints that
Claude Code / Gemini / Cursor deliver automatically are surfaced here as a single
standing line instead (spec 362, FR-011 documented gap): **before a commit run
`/verify`** (or `/project-commit` for the full pipeline); **after opening a PR run
`/post-pr-review-monitor`**; **when context is high run `/checkpoint`**. Run
`/help` for anything else.

## Command Index

<!-- BEGIN COMMAND INDEX (generate_commands_doc.py --inject-guides) -->
<!-- markdownlint-disable MD013 -->

- **Git & PRs**: `/address-pr-comments` · `/auto-issue-dev` · `/bot-pr-triage` · `/branch-clean` · `/clean-pr-from-stale-base` · `/commit-issue-sync` · `/locate-missing-artifact-across-git` · `/merge-stacked-pr-chain` · `/post-pr-review-monitor` · `/pr-issue-sync` · `/pr-review` · `/project-commit` · `/repo-hygiene` · `/reset-reapply-clean-pr` · `/triage-bot-pr-flood`
- **Documentation**: `/docs-all` · `/docs-diagrams` · `/docs-improve` · `/docs-readme`
- **Security**: `/ci-workflow-trigger-security` · `/diff-security-review` · `/docker-published-port-firewall-audit` · `/llm-output-path-traversal-audit` · `/mcp-server-security-audit` · `/secret-safe-upstream-proxy` · `/secure-comment-triggered-workflow` · `/security-finding-refutation` · `/security-finding-triage`
- **Planning & Specs**: `/architecture-decision-tradeoff-table` · `/auto-dev-issue-prep` · `/issue-prioritize` · `/issue-triage` · `/plan-manage` · `/research-validate-design` · `/spec-review` · `/speckit-implement-review` · `/verify-premise` · `/wire-new-field-end-to-end`
- **Skill Authoring**: `/ai-hooks-integration` · `/meta-prompt-optimize` · `/skill-evolve`
- **CI/CD, Testing & Quality**: `/a11y-audit` · `/browser-test` · `/ci-lint-config-drift` · `/ci-setup` · `/live-data-validation` · `/performance-check` · `/pin-known-bug-test-survives-fix` · `/refactor-go` · `/refactor-node` · `/refactor-python` · `/refactor-shell` · `/refactor-terraform` · `/reproduce-gated-ci-failure-locally` · `/statistical-test-fixture-variance` · `/ux-review` · `/verify`
- **Infrastructure & Config**: `/api-bulk-endpoint-optimization` · `/app-native-config-validation` · `/cli-help-before-dependency-checks` · `/containerized-internal-service-probe` · `/debug-layered-config-substitution` · `/deploy-drift-root-cause` · `/diagnose-stalled-background-process` · `/headless-llm-cli-seam` · `/ingestion-table-idempotency` · `/out-of-band-cache-warm` · `/pass-cli` · `/retire-component-cleanup` · `/scaffold` · `/shell-pipefail-subshell-audit` · `/shell-sete-silent-abort-audit` · `/sync-configs` · `/version-pin`
- **Meta & Orchestration**: `/antipattern-detect` · `/checkpoint` · `/code-quality` · `/dashboard` · `/health-check` · `/help` · `/learning-loop` · `/memory-log-compress` · `/session-memory-compress` · `/token-benchmark` · `/token-economy`
- **Uncategorized**: `/pr-regression-smoke`

Run `/help <query>` for descriptions and when-to-use.

<!-- markdownlint-enable MD013 -->
<!-- END COMMAND INDEX -->
