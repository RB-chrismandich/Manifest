# Gemini Orchestration Guide

This document defines OMP-native sub-agent dispatch, planning, and validation.

**Symlink Strategy**: The `.gemini/` directory shares most assets with `.claude/`
via symlinks. Prompts, configuration, scripts, plans, and all skills
point back to their canonical locations under `~/.claude/`. Only this guide
(`GEMINI.md`) and `settings.json` are Gemini-specific. This avoids duplication
and ensures both agents always operate from the same orchestration rules and
validation criteria.

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
- Pin dispatched sub-agents to Sonnet by default; never inherit the session's model.

`/token-conserve` re-asserts this mode if drift is noticed mid-session.

## OMP Sub-Agent Dispatch

OMP `task` and `hub` are the only interactive sub-agent contract. For workload
decomposition, when work has independent units, submit all ready units in one
`task` call, in waves of at most 32. Choose `scout` for read-only exploration,
`reviewer` for quality review, `security-reviewer` for security review, `sonic`
only for mechanical work, and omit `agent` for default implementation work.

Children execute their assigned unit directly and never redispatch. Use `hub`
only to coordinate or wait. The parent validates evidence, resolves material
disagreement, and aggregates results. If `task` is unavailable, execute inline
and report `DEGRADED`; never fall back to a provider CLI.

---

## Proactive Decision Framework

Use risk-based review routing. One capable reviewer is the default. Escalate
only for a trust-boundary change, destructive behavior, broad compatibility or
deployment change, conflicting evidence or unresolved uncertainty, or a
codebase-wide investigation with genuinely independent tracks. File, package,
module, language, keyword, and independent-unit counts never trigger
independent review.

---

## Validation Criteria

- **Tier 1 (blocking)**: security, error handling, breaking
  changes. **Tier 2 (advisory)**: bugs, performance, maintainability, tests.
- Authoritative weights: `~/.gemini/config/validation_criteria.yml` (symlink to `~/.claude/config/`).

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
`~/.claude/config/knowledge_base.yml` (guardrail tags: arch, async-state,
error-handling, security, dependency, iteration). Full reference:
`~/.claude/references/antipatterns.md`. Pre-write doctrine (13 articles, size
ceilings, per-language annexes): `~/.claude/references/code-constitution.md`,
enforced by `constitution_check.py`. On-demand deep audit: `/ai-code-audit`.

---

## Skills

Gemini CLI discovers skills from `~/.gemini/skills/` (symlinked from `~/.claude/skills/`).
Those skills use the shared OMP-native contract to decompose ready independent
work; that workload fan-out is distinct from the independent-review gate above.

### Available Skills

| Skill | Description | Parallel Agents |
|-------|-------------|-----------------|
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect codebase antipatterns and suggest fixes | NO |
| `/session-checkpoint` | Save context checkpoint for session continuity | NO |
| `/ci-setup` | Configure CI/CD pipelines for target repository | NO |
| `/code-audit` | Auto-triggered security and quality checks | AUTO |
| `/docs-generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL |
| `/docs-improve-readme` | Improve README documentation | NO |
| `/env-check` | Verify CLI tools, auth, config, MCP, symlinks | NO |
| `/issue-prioritize` | Score and rank open issues by impact | CONDITIONAL |
| `/issue-triage` | Linear issue audit with duplicate detection | CONDITIONAL |
| `/learning-capture` | Capture structured lessons learned | NO |
| `/performance-check` | Core Web Vitals and bundle analysis | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/git-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL |
| `/go-refactor` | Go codebase security and quality analysis | CONDITIONAL (risk-based) |
| `/node-refactor` | Node.js/TypeScript security and quality analysis | CONDITIONAL (risk-based) |
| `/python-refactor` | Python codebase security and quality analysis | CONDITIONAL (risk-based) |
| `/shell-refactor` | Bash/Shell script security and quality analysis | CONDITIONAL (risk-based) |
| `/terraform-refactor` | Terraform IaC security and modularity analysis | CONDITIONAL (risk-based) |
| `/project-scaffold` | Initialize new project with quality gates and Manifest integration | NO |
| `/config-audit` | Detect cross-platform config drift | NO |
| `/ux-review` | UX/accessibility/performance audit | NO |
| `/project-verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |

### Skill Usage

Skills are invoked as slash commands in Gemini CLI. Representative examples:

```bash
/python-refactor src/          # language analysis (also go/node/shell/terraform)
/git-commit "Add feature"  # commit pipeline (omit message to auto-generate)
/project-verify                        # linters, tests, security scans in parallel
/docs-improve-readme                   # docs (also /docs-generate-diagrams, /docs-improve)
/issue-triage                  # Linear backlog audit (also /issue-prioritize)
/plan-manage                   # plan lifecycle
/env-check                  # env sanity (also /config-audit)
/session-checkpoint                    # high-context save (also /learning-capture)
```

### Security Review Skill

The `code-audit` skill (symlinked from `~/.claude/skills/code-audit/SKILL.md`)
activates only for an explicit security review request or confirmed changed
behavior at a security boundary. Keywords, file size, function/class counts,
and complexity metrics alone do not activate it; feedback remains inline and
non-blocking.

---

## Configuration Files

All configuration is symlinked from `~/.claude/` to ensure both Claude and Gemini
operate from identical orchestration rules.

| File | Purpose |
|------|---------|
| `~/.claude/config/command_config.yml` | Thresholds, tool policies, error recovery |
| `~/.claude/config/validation_criteria.yml` | Tier 1/Tier 2 validation rules with command overrides |
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis template |
| `~/.claude/prompts/validation.md` | Validation criteria template |

> Accessible locally via `~/.gemini/config/` and `~/.gemini/prompts/` symlinks.

---

## File Structure

```text
~/.gemini/
├── GEMINI.md                        # This orchestration guide
├── skills/ -> ~/.claude/skills/     # Symlinked shared skills (source of truth)
├── prompts/ -> ~/.claude/prompts/   # Symlinked shared templates
├── config/ -> ~/.claude/config/     # Symlinked shared configs
├── scripts/ -> ~/.claude/scripts/   # Symlinked shared scripts
├── .plans/ -> ~/.claude/.plans/     # Symlinked shared plans
└── settings.json                    # Gemini CLI project settings
```

---

## Plan Management

Plans are markdown files in `~/.claude/.plans/` (symlinked at `~/.gemini/.plans/`)
named `YYYYMMDD-short-description.md` (copy `TEMPLATE.md`). Lifecycle:
CREATE -> ACTIVE (check off deliverables as completed) -> `.archive/` when done
or `.abandoned/` if superseded. Review existing plans before creating new ones;
plans untouched 7+ days should be updated, completed, or abandoned. Use
`/plan-manage` for orchestrated create/review/execute/archive/abandon.

## Command Index

<!-- BEGIN COMMAND INDEX (generate_commands_doc.py --inject-guides) -->
<!-- markdownlint-disable MD013 -->

- **Git & PRs**: `/branch-clean` · `/git-commit` · `/git-find-artifact` · `/issue-dev-auto` · `/issue-sync-commit` · `/issue-sync-pr` · `/pr-address-comments` · `/pr-clean-base` · `/pr-merge-stacked` · `/pr-monitor` · `/pr-reset-reapply` · `/pr-review` · `/pr-triage-bots` · `/repo-clean`
- **Documentation**: `/docs-all` · `/docs-generate-diagrams` · `/docs-improve` · `/docs-improve-readme`
- **Security**: `/ci-audit-triggers` · `/ci-harden-workflow` · `/docker-audit-firewall` · `/llm-audit-traversal` · `/mcp-audit` · `/security-harden-proxy` · `/security-refute-findings` · `/security-review-diff` · `/security-triage-findings`
- **Planning & Specs**: `/data-wire-field` · `/design-validate` · `/issue-prep-auto` · `/issue-prioritize` · `/issue-triage` · `/plan-manage` · `/premise-verify` · `/spec-audit-tasks` · `/spec-decide-tradeoffs` · `/spec-review`
- **Skill Authoring**: `/ai-hooks-integration` · `/prompt-optimize` · `/skill-evolve`
- **CI/CD, Testing & Quality**: `/a11y-audit` · `/ai-code-audit` · `/ci-diagnose-drift` · `/ci-reproduce-failure` · `/ci-setup` · `/data-validate-live` · `/go-refactor` · `/node-refactor` · `/performance-check` · `/project-verify` · `/python-refactor` · `/shell-refactor` · `/smoke-manage` · `/terraform-refactor` · `/test-pin-bug` · `/test-vary-fixtures` · `/ux-review`
- **Infrastructure & Config**: `/api-optimize-bulk` · `/cache-warm-oob` · `/cli-audit-help` · `/config-audit` · `/config-debug-substitution` · `/config-validate-native` · `/data-design-ingestion` · `/deploy-diagnose-drift` · `/deploy-retire-component` · `/docker-compose-commandments` · `/docker-probe-internal` · `/llm-invoke-stdin` · `/pass-cli` · `/process-diagnose-stall` · `/project-scaffold` · `/shell-audit-errexit` · `/shell-audit-pipefail` · `/version-pin`
- **Meta & Orchestration**: `/antipattern-detect` · `/code-audit` · `/env-check` · `/help` · `/learning-capture` · `/memory-compress` · `/session-checkpoint` · `/token-benchmark` · `/token-conserve`
- **Uncategorized**: `/automation-rework-breakeven` · `/code-audit-constitution` · `/code-to-design` · `/delegate` · `/delegate-setup` · `/deploy-reconcile` · `/design-loop` · `/design-md` · `/enhance-prompt` · `/extract-design-md` · `/extract-static-html` · `/false-green-check-audit` · `/generate-design` · `/i-have-adhd` · `/issue-manage` · `/lifecycle-run` · `/loop-scaffold` · `/manage-design-system` · `/pr-manage` · `/pr-smoke` · `/react-components` · `/react-native` · `/react-vite-dashboard` · `/refactor` · `/remotion` · `/render-verify` · `/review-round` · `/screen-prompts` · `/shadcn-ui` · `/shell-audit` · `/spec-amend` · `/spec-implement-loop` · `/stitch-loop` · `/taste-design` · `/test-isolate-ambient` · `/ui-delivery` · `/ui-verification` · `/upload-to-stitch`

Run `/help <query>` for descriptions and when-to-use.

<!-- markdownlint-enable MD013 -->
<!-- END COMMAND INDEX -->
