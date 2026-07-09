# Claude Orchestration Guide

This document defines how Claude should leverage parallel LLM agents
(Gemini, Cursor, Claude CLI, Codex, Antigravity) for cross-verification, planning, and validation.

## Token Economy (always on)

Apply at all times, in every session:

- Lead with the result. No filler ("Sure", "Here's the…"), no closing summaries.
- Match response length to the task; don't re-explain code you just wrote unless asked.
- Use programmatic edit tools for targeted edits; never reprint a whole file for a small change.
- If an implementation detail is genuinely ambiguous, ask ONE targeted question instead of guessing.
- Read what a change depends on (types, signatures, callers); skip speculative
  whole-tree crawls and re-reads of unchanged files. Don't starve context —
  a wrong edit costs more than one extra dependency read.

`/token-conserve` re-asserts this mode if drift is noticed mid-session.

## Parallel Agent Script

**Location**: `~/.claude/scripts/parallel_agent.py`

### Quick Usage

**IMPORTANT**:

- Always use **absolute paths** when specifying files to analyze or review
  (agents run from different working directories).
- Always use a **large timeout** (600-900s) for complex analyses; the 120s
  default is often insufficient.

Default MCP/tool routing — use the matching tool when the task domain matches:

- **Context7 MCP** — library/API docs, code generation, setup, configuration
- **Sentry MCP** — production/runtime errors, stack traces, release regressions
- **Linear MCP** — issue requirements, acceptance criteria, project planning
- **Semgrep CLI** (`semgrep scan`) — local SAST, vulnerability and secrets checks
- **DeepWiki MCP** — unfamiliar repos, dependency internals, upstream API contracts
- **Glean MCP** — internal team knowledge, runbooks, ADRs
- **Google Dev Docs MCP** — Firebase/Cloud/Android/Maps documentation
- **Atlassian MCP** — Jira issues, Confluence pages, Compass components
- **Apify MCP** — web scraping/crawling for structured external data
- **OpenTofu MCP** — Terraform/OpenTofu registry, provider/module docs

```bash
# Basic code review with JSON output (all 5 agents, 10 min timeout)
~/.claude/scripts/parallel_agent.py --json --timeout 600 --review /absolute/path/to/file

# Generic prompt to all agents
~/.claude/scripts/parallel_agent.py --json "Your question here"

# Full analysis with validation and model selection (15 min timeout)
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 900 --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file
```

## Reference Index

Read on demand (NOT auto-loaded). You MUST read the reference before related tasks:

- `~/.claude/references/parallel-agent.md` — Read for flag specs, JSON schema validation, or resolving Credit Exhaustion.
- `~/.claude/references/orchestration.md` — Read when running multi-agent validation or debugging cross-verification failures.
- `~/.claude/references/git-platform.md` — Read when automating PRs, branch detection, or git_ops failures.
- `~/.claude/references/layout.md` — Read when modifying config trees or mapping file locations.
- `~/.claude/references/sub-agent-dispatch.md` — Read before a skill dispatches sub-agents: native Task vs
  `parallel_agent.py`, when-to-dispatch threshold, cross-platform fallback.
- `~/.claude/references/spec-artifact-discovery.md` — Read before a spec-* skill (spec-review,
  spec-audit-tasks, spec-decide-tradeoffs) reads planning artifacts: speckit vs superpowers layout
  detection, discovery precedence, and where each skill records/audits.
- `~/.claude/references/antipatterns.md` — Read before writing or refactoring code:
  guardrail registry (detection cues + prevention rules).

## Proactive Coding Guardrails (always on)

While writing: propagate error signals (never log-and-drop); validate inputs at
boundaries; secrets from env only; await/route every async op; pair
setup/teardown; serialize shared writes; refactor before accreting; no
speculative guards, single-use abstractions, or dead code; verify new deps
exist. When refining, NEVER silently remove security controls or validation.
Registry: `~/.claude/config/knowledge_base.yml`; `/ai-code-audit` = full audit.

---

## Proactive Decision Framework

### ALWAYS Use Parallel Agents For

1. **Security-sensitive code changes**
   - Authentication/authorization logic
   - Input validation and sanitization
   - Cryptographic operations
   - Secret handling

2. **Architectural decisions**
   - New system components
   - API design changes
   - Database schema modifications
   - Service integration patterns

3. **Large file modifications (>200 lines)**
   - Complex refactoring
   - Major feature additions
   - Performance-critical code

4. **Critical business logic**
   - Payment processing
   - User data handling
   - Compliance-related code

### CONSIDER Parallel Agents For

- Complex refactoring with multiple affected files
- New feature implementation
- Performance optimization
- Debugging difficult issues

### SKIP Parallel Agents For

- Typo fixes, comments, formatting
- Single-line changes
- Documentation updates
- Simple variable renames

---

## Validation Criteria

- **Tier 1 (blocking)**: cross-verification, security, error handling, breaking
  changes. **Tier 2 (advisory)**: bugs, performance, maintainability, tests.
- Authoritative weights: `~/.claude/config/validation_criteria.yml`. Consensus
  thresholds and verdict rules (`APPROVED`/`NEEDS_REVIEW`/`BLOCKED`):
  `~/.claude/references/orchestration.md`.

---

## Skills

Skills live in `~/.claude/skills/` (70+ skills, deployed from the repo's
`.skillshare/skills/`). Each skill's `SKILL.md` frontmatter (`name`,
`description`) is the **authoritative registry** — Claude Code auto-loads every
description at session start, so no table is duplicated here. Per-skill
parallel-agent policy (always/conditional/never) lives in
`~/.claude/config/command_config.yml` under `tool_policies`.

Common entry points: `/git-commit` (full commit pipeline), `/project-verify`
(lint + test + scan), `/refactor-<lang>` (security/quality roadmap, parallel
agents ALWAYS), `/docs-all` (refresh all docs), `/plan-manage` (plan
lifecycle), `/env-check` (env sanity), `/session-checkpoint` (high-context save),
`/version-pin <file>` (auto-fix; `--check` = warn-only save-hook mode),
`/graphify` (map a codebase/docs into a queryable knowledge graph).

**Graphify** is a managed *tool*, not a parallel-orchestration agent: the
`graphify` CLI (installed by bootstrap when enabled) and its `/graphify` skill
are toggled via `--enable-graphify`/`--disable-graphify` (default: enabled), but
graphify never participates in `parallel_agent.py` consensus and is not counted
toward orchestration readiness.

**CLI tool** (installed to `~/.local/bin/`): `sync-skills` — push
`.skillshare/skills/` changes to all home targets (daily skill dev workflow).

### Auto-Triggered Skill

`code-audit` auto-triggers on security-sensitive patterns (auth, crypto,
secrets, input validation) or complexity (>500 lines, >10 functions, or >5
classes per file), giving inline feedback without blocking the workflow.

---

## Plan Management

Plans are markdown files in `~/.claude/.plans/` named
`YYYYMMDD-short-description.md` (copy `TEMPLATE.md`). Lifecycle:
CREATE → ACTIVE (check off deliverables as completed) → `.archive/` when done
or `.abandoned/` if superseded. Review existing plans before creating new ones;
plans untouched 7+ days should be updated, completed, or abandoned. Use
`/plan-manage` for orchestrated create/review/execute/archive/abandon.
