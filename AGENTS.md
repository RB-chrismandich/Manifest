# AGENTS.md

> Repository context and guidance for AI coding agents (Cursor, Claude Code, Codex, Antigravity, etc.)

**Last Updated**: 2026-06-10
**Audience**: AI assistants (Cursor Agent, Claude Code, Codex CLI, Antigravity), contributors
**Purpose**: Provide AI agents with repository structure, deployment process, and testing guidelines

---

This file provides guidance to AI coding agents when working with code in this repository.
It follows the [AGENTS.md standard](https://agents.md/) for unified coding agent instructions.

## Risk-based review routing

Use a single capable reviewer by default. Independent review is risk-based:
escalate only for a trust-boundary change, destructive behavior, broad
compatibility or deployment impact, conflicting evidence or unresolved
uncertainty, or genuinely independent codebase-wide tracks. Counts of files,
packages, modules, languages, keywords, and units do not independently escalate.

## Token Economy (always on)

Apply at all times, in every session:

- Lead with the result. No filler ("Sure", "Here's the…"), no closing summaries.
- Match response length to the task; don't re-explain code you just wrote unless asked.
- Use programmatic edit tools for targeted edits; never reprint a whole file for a small change.
- If an implementation detail is genuinely ambiguous, ask ONE targeted question instead of guessing.
- Read what a change depends on (types, signatures, callers); skip speculative
  whole-tree crawls and re-reads of unchanged files. Don't starve context —
  a wrong edit costs more than one extra dependency read.
- Default dispatched agents to Sonnet through the current host's native control;
  OMP uses `task.agentModelOverrides`, never a task-item `model` field.

## MCP Default Policy

Default MCP/tool routing — use the matching tool when the task domain matches
**and that server is actually registered**. The list below is a domain map, not a
promise of availability, so check your own tool list before routing to one.

**Context7 is the only server registered by default**, on every platform that
registers any (Claude via `mcp_user_servers.json`, Cursor via
`configs/cursor/mcp.json`; Codex and
Antigravity symlink the config and register nothing). One registry field —
`shipped:` in `mcp_servers.yml` — decides this for all of them.

Everything else below is catalog-only: offered by `./bootstrap.sh --install-mcp`,
absent until you ask for it, because each remote server costs an `npx mcp-remote`
subprocess per agent invocation. Semgrep is a CLI, so it is available wherever it
is installed, independent of MCP.

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

This repository manages AI coding workflow configuration for deployment to
`~/.claude/` (and mirrored to `~/.cursor/`, `~/.codex/`, and
`~/.antigravity/`; Antigravity's CLI also reads `~/.gemini/GEMINI.md`). It contains OMP-native orchestration guides, skills,
prompts, and retained single-provider scripts.

## Repository Structure

```text
.
├── configs/                         # Deployment source configuration
│   ├── claude/                      # Shared configuration and Claude guide
│   ├── cursor/                      # Cursor rules and configuration
│   ├── codex/                       # Codex guide
│   └── antigravity/                 # Antigravity guide
├── bootstrap.sh                     # macOS/Linux bootstrap entry point
├── bootstrap/                       # Deployment implementation
├── AGENTS.md                        # Shared agent instructions
└── CLAUDE.md                        # Claude Code-specific instructions
```

The per-harness deployed paths and links are documented in
`~/.claude/references/layout.md`; do not infer them from this source tree.

## Bootstrap

Bootstrap handles installation, deployment, and authentication. Use
`./bootstrap.sh` for standard setup; read the on-demand
`~/.claude/references/layout.md` for supported platforms, options, and
harness-specific deployment details.

## Manual Deployment

Bootstrap is the supported installation path. For configuration layout,
platform-specific links, and manual-deployment caveats, read
`~/.claude/references/layout.md`.

## Key Files

| File | Purpose |
|------|---------|
| `configs/claude/CLAUDE.md` | Main orchestration guide for Claude Code |
| `configs/cursor/rules/orchestration.mdc` | Main orchestration guide for Cursor (always-on rule) |
| `configs/antigravity/GEMINI.md` | Main orchestration guide for Antigravity (deployed to `~/.gemini/GEMINI.md`) |
| `configs/codex/AGENTS.md` | Main orchestration guide for Codex CLI |
| `configs/claude/scripts/manifest_cli/` | Manifest CLI (`manifest smoke`, `manifest skill-run`, `manifest doctor`) |
| `configs/claude/config/command_config.yml` | Thresholds, tool policies, model selection, error recovery |
| `configs/claude/config/validation_criteria.yml` | Tier 1 (critical) and Tier 2 (quality) validation rules |

## Available Skills

Skills are maintained in plugin bundles; harnesses consume them through their
native plugin or generated-rule mechanisms. Read `~/.claude/references/layout.md`
for current source and deployment paths.
Skills are invoked as slash commands (e.g., `/python-refactor src/`).

### Skill Reference

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/git-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/docs-improve-readme` | Improve README documentation | NO |
| `/docs-generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/docs-all` | Run docs-improve-readme/docs-generate-diagrams/docs-improve as sub-agents in one pass | CONDITIONAL |
| `/python-refactor` | Python codebase security and quality analysis | CONDITIONAL (risk-based) |
| `/shell-refactor` | Bash/Shell script security and quality analysis | CONDITIONAL (risk-based) |
| `/node-refactor` | Node.js/TypeScript codebase security and quality analysis | CONDITIONAL (risk-based) |
| `/go-refactor` | Go codebase security and quality analysis | CONDITIONAL (risk-based) |
| `/terraform-refactor` | Terraform/OpenTofu IaC security, modularity, and quality analysis | CONDITIONAL (risk-based) |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact/urgency/readiness/risk | CONDITIONAL |
| `/plan-manage` | Plan lifecycle with OMP-native independent review | CONDITIONAL |
| `/smoke-manage` | Catalog-driven smoke tests; UI steps run via browser-use `mode: agent` | NO |
| `/session-checkpoint` | Create compact checkpoint summary when context is high | NO |
| `/env-check` | Verify CLI tools, auth, config syntax, MCP, symlinks | NO |
| `/config-audit` | Detect cross-platform config drift and broken symlinks | NO |
| `/version-pin` | Enforce specific, hashed version pins in dependency files (auto-fix on demand; warn-only save hook) | ALWAYS (Tier 1) |
| `/pr-review` | Review all open PRs and recommend a disposition per PR (analysis-only) | NO |
| `/branch-clean` | Prune merged/gone/stale branches safely (dry-run by default, local-only) | CONDITIONAL (--apply) |
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run by default); requires SkillClaw enabled | NO |
| `/pass-cli` | Retrieve credentials from Proton Pass vaults via `pass-cli` agent CLI | NO |
| `/spec-review` | Independent Antigravity (agy) cross-reference of spec/plan/tasks for internal consistency; on-demand or via fail-open PostToolUse save hook (content-hash debounced, detached); analysis-only; works with speckit and design-doc layouts; silent-mode findings land in `.spec-review/feedback.md` | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect recurring antipatterns from lint, test, and review feedback | NO |
| `/ci-setup` | Configure CI/CD pipelines for a target repository (GitHub Actions or GitLab CI) | NO |
| `/code-audit` | Auto-triggered security and quality checks | AUTO (always when triggered) |
| `/learning-capture` | Capture structured lessons learned | NO |
| `/performance-check` | Frontend performance audit: bundle size, Core Web Vitals, caching | NO |
| `/project-scaffold` | Initialize new projects with quality gates and Manifest integration | NO |
| `/ux-review` | UX audit: accessibility, responsive design, performance budgets | NO |
| `/project-verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |

**Skills are plugin bundles**: `/<bundle>:<name>`; refresh Claude bundles with
`claude plugin update <bundle>@manifest`. Other harnesses use their native
plugin, generated-rule, or shared-catalog mechanisms; see the Layout Reference.

### Cursor Rules

All Cursor rules are auto-generated from SKILL.md files using `generate_cursor_rules.sh`.
Each skill produces a corresponding `.mdc` rule in `configs/cursor/rules/`.

The full rule set (one `.mdc` per skill, plus `orchestration` and
`commands-index`) lives in `configs/cursor/rules/` — regenerate with
`generate_cursor_rules.sh`; do not hand-edit generated rules.

### Platform-Specific Notes

Read `~/.claude/references/layout.md` for each harness's native plugin,
generated-rule, or shared-catalog mechanism. Do not assume that every harness
loads skills through a symlink to `~/.claude/`.

## Native Sub-Agent Dispatch

Use the current host's supported native mechanism. OMP parents dispatch work
with `task`, selecting the narrowest suitable agent; the parent validates
evidence and aggregates results. Claude Code parents use discovered native
Agents and background collection. Preserve platform boundaries and do not
guess aliases. The authoritative shared contract is
`~/.claude/references/sub-agent-dispatch.md`;
it defines child limits, the narrow delegate-runner exception, and `DEGRADED`
behavior.

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
`plugins/manifest-workspace/skills/learning-capture/data/seed.jsonl` bundled seed
plus the XDG-owned `manifest/knowledge/entries.jsonl` store (guardrail tags: arch,
async-state, error-handling, security, dependency, iteration). Full reference:
`configs/claude/references/antipatterns.md`. Pre-write doctrine (13 articles, size
ceilings, per-language annexes): `configs/claude/references/code-constitution.md`,
enforced by `configs/claude/scripts/constitution_check.py`. On-demand deep audit:
`/ai-code-audit`.

---

## Coding Standards

**Script language: Bash (`.sh`) and Python (`.py`) are both Active — primary.**
Neither is legacy. `configs/claude/scripts/` holds 23 `.sh` files beside the
`.py` helpers, and the whole bootstrap surface (`bootstrap.sh`, `bootstrap/lib/*.sh`)
is Bash by design. **Do not propose blanket `.sh`→`.py` migrations, or the
reverse.** Match the convention of the code you are changing; when adding a new
script, follow the directory it lives in. `docs/CODING_STANDARDS.md` sections
"Bash (Active — primary)" and "Python (Active — primary)" are authoritative.

This is stated normatively here because it is the rule agents most often
violate — see #828, where one skill file drew 66 PRs, several of which
rewrote a constraint warning against exactly this assumption into its inverse.

Per-language coding standards and how they are enforced (editor → edit-time →
commit → CI) are documented in
[docs/CODING_STANDARDS.md](docs/CODING_STANDARDS.md). An advisory PostToolUse hook
lints each file you edit; the CI gate runs `pre-commit` on changed files.

## Testing Changes

```bash
# Validate YAML configs
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/validation_criteria.yml'))"
```

## Plan Management

Implementation plans are tracked in `configs/claude/.plans/` (symlinked at `configs/cursor/.plans/`
and `configs/codex/.plans/`) as date-prefixed markdown files (`YYYYMMDD-description.md`).

Lifecycle: `CREATE -> ACTIVE -> COMPLETED (.archive/) or ABANDONED (.abandoned/)`

## Adding New Configuration

### Adding a Claude Code Skill

1. Add the skill under `plugins/<bundle>/skills/<skill-name>/SKILL.md`
   (canonical source); generated mirrors are not edited directly.
2. Add its tool policy to `configs/claude/config/command_config.yml` when
   needed, then refresh the relevant native plugin deployment.

### Adding a Cursor Rule

1. Create an `.mdc` file in `configs/cursor/rules/` (e.g., `my-rule.mdc`)
2. Add YAML frontmatter with `description`, `globs`, and `alwaysApply`
3. Rule auto-attaches when files matching `globs` are referenced (after deploying)

---

## Related Documents

- [README.md](README.md) - Project overview and quick start
- [CLAUDE.md](CLAUDE.md) - Claude Code-specific project instructions
- [docs/README.md](docs/README.md) - Documentation hub
- [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) - First-time setup walkthrough
- [docs/configuration/README.md](docs/configuration/README.md) - Complete configuration reference
- [docs/diagrams/README.md](docs/diagrams/README.md) - Visual system documentation
- [configs/claude/.plans/README.md](configs/claude/.plans/README.md) - Plan management quick reference

## Workflow Reminders

Use these reminders as guidance, not as a claim about a host's event-hook
capabilities: before a commit run `/project-verify` (or `/git-commit` for the
full pipeline); after opening a PR run `/pr-monitor`; when context is high run
`/session-checkpoint`. Run `/help` for anything else.

## Command Index

<!-- BEGIN COMMAND INDEX (generate_commands_doc.py --inject-guides) -->
<!-- markdownlint-disable MD013 -->

- **Git & PRs**: `/branch-clean` · `/git-commit` · `/git-find-artifact` · `/issue-dev-auto` · `/issue-sync-commit` · `/issue-sync-pr` · `/pr-address-comments` · `/pr-clean-base` · `/pr-merge-stacked` · `/pr-monitor` · `/pr-reset-reapply` · `/pr-review` · `/pr-triage-bots` · `/repo-clean`
- **Documentation**: `/docs-all` · `/docs-generate-diagrams` · `/docs-improve` · `/docs-improve-readme`
- **Security**: `/ci-audit-triggers` · `/ci-harden-workflow` · `/docker-audit-firewall` · `/llm-audit-traversal` · `/mcp-audit` · `/security-harden-proxy` · `/security-refute-findings` · `/security-review-diff` · `/security-triage-findings`
- **Planning & Specs**: `/data-wire-field` · `/design-validate` · `/issue-prep-auto` · `/issue-prioritize` · `/issue-triage` · `/plan-manage` · `/premise-verify` · `/spec-audit-tasks` · `/spec-decide-tradeoffs` · `/spec-review`
- **Skill Authoring**: `/ai-hooks-integration` · `/prompt-optimize` · `/skill-evolve`
- **CI/CD, Testing & Quality**: `/a11y-audit` · `/ai-code-audit` · `/ci-diagnose-drift` · `/ci-reproduce-failure` · `/ci-setup` · `/data-validate-live` · `/go-refactor` · `/node-refactor` · `/performance-check` · `/project-verify` · `/python-refactor` · `/shell-refactor` · `/smoke-manage` · `/terraform-refactor` · `/test-pin-bug` · `/test-vary-fixtures` · `/ux-review`
- **Infrastructure & Config**: `/api-optimize-bulk` · `/cache-warm-oob` · `/cli-audit-help` · `/config-audit` · `/config-debug-substitution` · `/config-validate-native` · `/data-design-ingestion` · `/deploy-diagnose-drift` · `/deploy-retire-component` · `/docker-compose-commandments` · `/docker-probe-internal` · `/llm-invoke-stdin` · `/pass-cli` · `/process-diagnose-stall` · `/project-scaffold` · `/renovate-config` · `/shell-audit-errexit` · `/shell-audit-pipefail` · `/version-pin`
- **Meta & Orchestration**: `/antipattern-detect` · `/code-audit` · `/env-check` · `/help` · `/learning-capture` · `/memory-compress` · `/session-checkpoint` · `/token-benchmark` · `/token-conserve`
- **Uncategorized**: `/automation-rework-breakeven` · `/code-audit-constitution` · `/code-to-design` · `/delegate` · `/delegate-setup` · `/deploy-reconcile` · `/design-loop` · `/design-md` · `/enhance-prompt` · `/extract-design-md` · `/extract-static-html` · `/false-green-check-audit` · `/generate-design` · `/i-have-adhd` · `/issue-manage` · `/lifecycle-run` · `/loop-scaffold` · `/manage-design-system` · `/pr-manage` · `/pr-smoke` · `/react-components` · `/react-native` · `/react-vite-dashboard` · `/refactor` · `/remotion` · `/render-verify` · `/review-round` · `/screen-prompts` · `/shadcn-ui` · `/shell-audit` · `/spec-amend` · `/spec-implement-loop` · `/stitch-loop` · `/taste-design` · `/test-isolate-ambient` · `/ui-delivery` · `/ui-verification` · `/upload-to-stitch`

Run `/help <query>` for descriptions and when-to-use.

<!-- markdownlint-enable MD013 -->
<!-- END COMMAND INDEX -->
