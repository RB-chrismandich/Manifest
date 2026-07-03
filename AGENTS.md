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
--enable-antigravity / --disable-antigravity  # Antigravity IDE (default: enabled)
--enable-graphify / --disable-graphify  # Graphify knowledge-graph CLI + /graphify skill (default: enabled)
--enable-skillclaw / --disable-skillclaw  # SkillClaw session capture (default: disabled)
--enable-browser-use / --disable-browser-use  # browser-use deps for smoke agent steps (default: disabled)
--enable-smoke / --disable-smoke     # smoke-test deps: Playwright+Chromium (default: disabled)
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
Skills are invoked as slash commands (e.g., `/python-refactor src/`).

### Skill Reference

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/git-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/docs-improve-readme` | Improve README documentation | NO |
| `/docs-generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/docs-all` | Run docs-improve-readme/docs-generate-diagrams/docs-improve as sub-agents in one pass | CONDITIONAL |
| `/python-refactor` | Python codebase security and quality analysis | ALWAYS |
| `/shell-refactor` | Bash/Shell script security and quality analysis | ALWAYS |
| `/node-refactor` | Node.js/TypeScript codebase security and quality analysis | ALWAYS |
| `/go-refactor` | Go codebase security and quality analysis | ALWAYS |
| `/terraform-refactor` | Terraform/OpenTofu IaC security, modularity, and quality analysis | ALWAYS |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact/urgency/readiness/risk | CONDITIONAL |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/smoke-manage` | Catalog-driven smoke tests; UI steps run via browser-use `mode: agent` | NO |
| `/session-checkpoint` | Create compact checkpoint summary when context is high | NO |
| `/env-check` | Verify CLI tools, auth, config syntax, MCP, symlinks | NO |
| `/config-audit` | Detect cross-platform config drift and broken symlinks | NO |
| `/version-pin` | Enforce specific, hashed version pins in dependency files (auto-fix on demand; warn-only save hook) | ALWAYS (Tier 1) |
| `/pr-review` | Review all open PRs and recommend a disposition per PR (analysis-only) | NO |
| `/branch-clean` | Prune merged/gone/stale branches safely (dry-run by default, local-only) | CONDITIONAL (--apply) |
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run by default); requires SkillClaw enabled | NO |
| `/pass-cli` | Retrieve credentials from Proton Pass vaults via `pass-cli` agent CLI | NO |
| `/spec-review` | Independent Antigravity (agy) cross-reference of spec/plan/tasks for internal consistency; on-demand or via fail-open PostToolUse save hook (content-hash debounced, detached); analysis-only; works with speckit and superpowers layouts; silent-mode findings land in `.spec-review/feedback.md` | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect recurring antipatterns from lint, test, and review feedback | NO |
| `/ci-setup` | Configure CI/CD pipelines for a target repository (GitHub Actions or GitLab CI) | NO |
| `/code-audit` | Auto-triggered security and quality checks | AUTO (always when triggered) |
| `/metrics-report` | Visualize agent efficiency metrics | NO |
| `/learning-capture` | Capture structured lessons learned | NO |
| `/performance-check` | Frontend performance audit: bundle size, Core Web Vitals, caching | NO |
| `/project-scaffold` | Initialize new projects with quality gates and Manifest integration | NO |
| `/ux-review` | UX audit: accessibility, responsive design, performance budgets | NO |
| `/project-verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |

**CLI tool** (installed to `~/.local/bin/`): `sync-skills` — sync `.skillshare/skills/`
to all home targets (daily skill dev workflow).

### Cursor Rules

All Cursor rules are auto-generated from SKILL.md files using `generate_cursor_rules.sh`.
Each skill produces a corresponding `.mdc` rule in `configs/cursor/rules/`.

The full rule set (one `.mdc` per skill, plus `orchestration` and
`commands-index`) lives in `configs/cursor/rules/` — regenerate with
`generate_cursor_rules.sh`; do not hand-edit generated rules.

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

## Proactive Coding Guardrails (always on)

Apply while writing or refactoring code, in every session:

- **Propagate error signals** — every catch rethrows, returns a typed
  error/fallback the caller must check, or routes to a central handler.
  Never log-and-fall-through.
- **Validate at boundaries** — type/presence/range checks at entry points;
  distinguish zero from missing; pass only validated values inward.
- **Secrets from the environment only** — no credential literals in source,
  tests, or .env.example; fail fast when required config is absent.
- **Handle the async lifecycle** — await or explicitly route every async
  operation; pair every listener/subscription/timer with its teardown;
  serialize or atomize concurrent writes to shared state.
- **Refactor before accreting** — extract the seam before adding to long
  functions/files; search for an existing helper before writing a new one.
- **No speculative code** — no guards for unreachable states, no single-use
  abstractions, no dead modules kept "for later".
- **Verify dependencies exist** — check the official registry (existence,
  maintenance, advisories) before adding any package.
- **Refinement safety** — when modifying existing code, NEVER remove security
  controls or validation without stating it in the change description.

Registry of anti-patterns (detection cues + prevention rules):
`configs/claude/config/knowledge_base.yml` (guardrail tags: arch, async-state,
error-handling, security, dependency, iteration). Full reference:
`configs/claude/references/antipatterns.md`. On-demand deep audit: `/ai-code-audit`.

---

## Coding Standards

Per-language coding standards and how they are enforced (editor → edit-time →
commit → CI) are documented in
[docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md). An advisory PostToolUse hook
lints each file you edit; the CI gate runs `pre-commit` on changed files.

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
`/project-verify`** (or `/git-commit` for the full pipeline); **after opening a PR run
`/pr-monitor`**; **when context is high run `/session-checkpoint`**. Run
`/help` for anything else.

## Command Index

<!-- BEGIN COMMAND INDEX (generate_commands_doc.py --inject-guides) -->
<!-- markdownlint-disable MD013 -->

- **Git & PRs**: `/branch-clean` · `/git-commit` · `/git-find-artifact` · `/issue-dev-auto` · `/issue-sync-commit` · `/issue-sync-pr` · `/pr-address-comments` · `/pr-clean-base` · `/pr-merge-stacked` · `/pr-monitor` · `/pr-reset-reapply` · `/pr-review` · `/pr-triage-bots` · `/repo-clean`
- **Documentation**: `/docs-all` · `/docs-generate-diagrams` · `/docs-improve` · `/docs-improve-readme`
- **Security**: `/ci-audit-triggers` · `/ci-harden-workflow` · `/docker-audit-firewall` · `/llm-audit-traversal` · `/mcp-audit` · `/security-harden-proxy` · `/security-refute-findings` · `/security-review-diff` · `/security-triage-findings`
- **Planning & Specs**: `/data-wire-field` · `/design-validate` · `/issue-prep-auto` · `/issue-prioritize` · `/issue-triage` · `/plan-manage` · `/premise-verify` · `/spec-decide-tradeoffs` · `/spec-review` · `/speckit-audit-tasks`
- **Skill Authoring**: `/ai-hooks-integration` · `/prompt-optimize` · `/skill-evolve`
- **CI/CD, Testing & Quality**: `/a11y-audit` · `/ai-code-audit` · `/ci-diagnose-drift` · `/ci-reproduce-failure` · `/ci-setup` · `/data-validate-live` · `/go-refactor` · `/node-refactor` · `/performance-check` · `/project-verify` · `/python-refactor` · `/shell-refactor` · `/smoke-manage` · `/terraform-refactor` · `/test-pin-bug` · `/test-vary-fixtures` · `/ux-review`
- **Infrastructure & Config**: `/api-optimize-bulk` · `/cache-warm-oob` · `/cli-audit-help` · `/config-audit` · `/config-debug-substitution` · `/config-validate-native` · `/data-design-ingestion` · `/deploy-diagnose-drift` · `/deploy-retire-component` · `/docker-probe-internal` · `/llm-invoke-stdin` · `/pass-cli` · `/process-diagnose-stall` · `/project-scaffold` · `/shell-audit-errexit` · `/shell-audit-pipefail` · `/version-pin`
- **Meta & Orchestration**: `/antipattern-detect` · `/code-audit` · `/env-check` · `/graphify` · `/help` · `/learning-capture` · `/memory-compress` · `/metrics-report` · `/session-checkpoint` · `/token-benchmark` · `/token-conserve`
- **Uncategorized**: `/deploy-reconcile` · `/lifecycle-run` · `/pr-smoke`

Run `/help <query>` for descriptions and when-to-use.

<!-- markdownlint-enable MD013 -->
<!-- END COMMAND INDEX -->
