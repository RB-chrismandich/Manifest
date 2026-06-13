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

`/token-economy` re-asserts this mode if drift is noticed mid-session.

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
- **Semgrep CLI** (`semgrep scan`) — local SAST, vulnerability and secrets
  checks (install: `brew install semgrep`)
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

# Quick query with lightweight models
~/.claude/scripts/parallel_agent.py --cursor-model mini --claude-model haiku "Quick question"

# Full analysis with validation and model selection (15 min timeout)
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 900 --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file

# Antigravity-only quick query
~/.claude/scripts/parallel_agent.py --antigravity-only --antigravity-model flash "Quick question"
```

## Reference Index

Read on demand (NOT auto-loaded). You MUST read the reference before related tasks:

- `~/.claude/references/parallel-agent.md` — Read for flag specs, JSON schema validation, or resolving Credit Exhaustion.
- `~/.claude/references/orchestration.md` — Read when running multi-agent validation or debugging cross-verification failures.
- `~/.claude/references/git-platform.md` — Read when automating PRs, branch detection, or git_ops failures.
- `~/.claude/references/layout.md` — Read when modifying config trees or mapping file locations.

---

## Proactive Decision Framework

### ALWAYS Use Parallel Agents For

1. **Security-sensitive code changes**
   - Authentication/authorization logic