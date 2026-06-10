# Claude Orchestration Guide

This document defines how Claude should leverage parallel LLM agents
(Gemini, Cursor, Claude CLI) for cross-verification, planning, and validation.

## Parallel Agent Script

**Location**: `~/.claude/scripts/parallel_agent.py`

### Quick Usage

**IMPORTANT**:

- Always use **absolute paths** when specifying files to analyze or review.
  Relative paths may fail as agents run from different working directories.
- Always use a **large timeout** (600-900 seconds) for complex analyses.
  The default 120s is often insufficient for thorough code review.
- Use **Context7 MCP** by default for library/API documentation, code generation,
  setup steps, and configuration guidance.
- Use **Sentry MCP** by default for production/runtime error investigation,
  stack traces, issue triage, and release regression analysis.
- Use **Linear MCP** by default for issue requirements, acceptance criteria,
  project context, and implementation planning.
- Use **Semgrep CLI** (`semgrep ci` or `semgrep scan`) for local SAST scanning,
  vulnerability detection, and secrets checks during code review and refactoring.
  Install: `brew install semgrep` or `pip install semgrep`.
- Use **DeepWiki MCP** by default for understanding unfamiliar repositories,
  dependency internals, and upstream API contracts.
- Use **Glean MCP** by default for internal team knowledge, runbooks, ADRs,
  and company-specific documentation.
- Use **Google Dev Docs MCP** for official Google platform documentation
  (Firebase, Cloud, Android, Maps) when working with Google services.
- Use **Atlassian MCP** for Jira issues, Confluence pages, and Compass
  components when the project uses Atlassian tools.
- Use **Apify MCP** for web scraping, data extraction, and crawling tasks
  that require fetching structured data from external websites.
- Use **OpenTofu MCP** for OpenTofu/Terraform registry lookups, provider and
  module documentation, resource and datasource reference when working with
  Infrastructure as Code.

```bash
# Basic code review with JSON output (all 3 agents, 10 min timeout)
~/.claude/scripts/parallel_agent.py --json --timeout 600 --review /absolute/path/to/file

# Generic prompt to all agents
~/.claude/scripts/parallel_agent.py --json "Your question here"

# Quick query with lightweight models
~/.claude/scripts/parallel_agent.py --cursor-model mini --claude-model haiku "Quick question"

# Full analysis with validation and model selection (15 min timeout)
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 900 --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file
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

### Tier 1: Critical (Always Check)

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Cross-Verification | 0.3 | Multiple agents agree on key findings |
| Security Issues | 0.3 | No injection, XSS, auth bypass, secrets |
| Error Handling | 0.2 | Proper exceptions, no silent failures |
| Breaking Changes | 0.2 | API compatibility, data migrations |

### Tier 2: Standard (Code Quality)

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Bug Detection | 0.25 | Logic errors, off-by-one, null refs |
| Performance | 0.25 | No O(n²), memory leaks |
| Maintainability | 0.25 | Clear naming, reasonable complexity |
| Test Coverage | 0.25 | Changes have corresponding tests |

---

## Skills

Claude Code skills are available in `~/.claude/skills/`.
These integrate with the parallel agent orchestration framework.

### Available Skills

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/project-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/docs-readme` | Improve README documentation | NO |
| `/docs-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/refactor-python` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | Bash/Shell script security and quality analysis | ALWAYS |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact/urgency/readiness/risk | CONDITIONAL |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration for create/review | CONDITIONAL |
| `/browser-test` | AI-powered E2E browser testing via browser-use YAML test prompts | CONDITIONAL |
| `/checkpoint` | Create compact checkpoint summary when context usage is high | NO |
| `/health-check` | Verify CLI tools, auth, config syntax, MCP, symlinks | NO |
| `/sync-configs` | Detect cross-platform config drift and broken symlinks | NO |
| `/sync-skills` | Sync .skillshare/skills/ to all home targets (daily skill dev workflow) | NO |
| `/version-pin` | Enforce specific, hashed version pins in dependency files | ALWAYS (Tier 1) |
| `/docs-all` | Run docs-readme/docs-diagrams/docs-improve as sub-agents in one pass | NO |
| `/pr-review` | Review all open PRs, recommend disposition per PR (analysis-only) | NO |
| `/branch-clean` | Prune merged/gone/stale branches safely (dry-run, local-only) | CONDITIONAL |
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run default) | NO |
| `/pass-cli` | Retrieve credentials from Proton Pass (auth is the user's step; PAT never stored) | NO |
| `/spec-review` | Independent Antigravity (agy) cross-reference of spec/plan/tasks for internal consistency; on-demand or via fail-open PostToolUse save hook (content-hash debounced, detached); analysis-only; engine: `~/.claude/scripts/spec_review.sh` (`--spec/--plan/--tasks/--silent/--format`) | NO |

### Command Usage

```bash
# Full commit pipeline with documentation generation
/project-commit "Add new feature"
/project-commit  # Auto-generate commit message

# Code analysis
/refactor-python src/
/refactor-shell .claude/scripts/

# Documentation
/docs-diagrams docs/ARCHITECTURE_DIAGRAMS.md
/docs-readme
/docs-improve docs/

# Issue management
/issue-triage                # Audit Linear backlog
/issue-prioritize            # Rank open issues by impact

# Plan management
/plan-manage create #42      # Create plan from issue
/plan-manage execute #42     # Execute plan deliverables

# Context management
/checkpoint                  # Save session state when context is high

# Skill sync (daily dev workflow)
sync-skills                  # Push .skillshare/skills/ changes to all home targets

# Dependency / repo hygiene
/version-pin requirements.txt          # Pin to specific version + hash (auto-fix)
/version-pin requirements.txt --check  # Warn-only (the save-hook mode)
/docs-all                              # Refresh all docs via sub-agents in one pass
/pr-review                             # Triage all open PRs (analysis-only)
/branch-clean                          # Preview prunable branches (dry-run)
/branch-clean --apply                  # Delete local candidates (with confirmation)
```

### Auto-Triggered Skill

The `code-quality` skill auto-triggers when detecting:

1. **Security patterns**: auth, crypto, secrets, input validation
2. **Complexity patterns**:
   - File > 500 lines
   - > 10 functions per file
   - > 5 classes per file

When triggered, it provides inline feedback without blocking user workflow.

---

## Plan Management

Implementation plans are tracked as markdown files in `~/.claude/.plans/`.

### Lifecycle

```text
CREATE → ACTIVE → COMPLETED (.archive/) or ABANDONED (.abandoned/)
```

1. **CREATE**: Copy `TEMPLATE.md`, save as `YYYYMMDD-short-description.md`
2. **ACTIVE**: Plan lives in `.plans/` root while work is in progress; check off deliverables as they are completed
3. **COMPLETED**: Move to `.archive/` when all deliverables are done
4. **ABANDONED**: Move to `.abandoned/` if superseded or no longer relevant

### Housekeeping Rules

- **Before creating a plan**: Review existing plans in `.plans/` to avoid duplicates
- **During implementation**: Check off deliverables (`- [x]`) as each is completed
- **Staleness threshold**: Plans untouched for 7+ days should be reviewed — either update, complete, or abandon them
- **Use `/plan-manage`** for orchestrated plan creation (parallel agents for cross-verified
  planning), review, archiving, and abandoning plans
