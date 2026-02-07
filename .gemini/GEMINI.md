# Gemini Orchestration Guide

This document defines how Gemini should leverage parallel LLM agents
(Gemini, Cursor, Claude CLI) for cross-verification, planning, and validation.

**Symlink Strategy**: The `.gemini/` directory shares most assets with `.claude/`
via symlinks. Prompts, configuration, scripts, plans, and the code-quality skill
all point back to their canonical locations under `~/.claude/`. Only this guide
(`GEMINI.md`), the TOML-based slash commands, and `settings.json` are
Gemini-specific. This avoids duplication and ensures both agents always operate
from the same orchestration rules and validation criteria.

## Parallel Agent Script

**Location**: `~/.claude/scripts/parallel_agent.sh`
(accessed via symlink at `~/.gemini/scripts/parallel_agent.sh`)

### Quick Usage

**IMPORTANT**:

- Always use **absolute paths** when specifying files to analyze or review.
  Relative paths may fail as agents run from different working directories.
- Always use a **large timeout** (600-900 seconds) for complex analyses.
  The default 120s is often insufficient for thorough code review.

```bash
# Basic code review with JSON output (all 3 agents, 10 min timeout)
~/.claude/scripts/parallel_agent.sh --json --timeout 600 --review /absolute/path/to/file

# Full analysis with validation and model selection (15 min timeout)
~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 900 \
  --cursor-model advanced --claude-model opus --analyze /absolute/path/to/file

# Generic prompt to all agents
~/.claude/scripts/parallel_agent.sh --json "Your question here"

# Quick query with lightweight models
~/.claude/scripts/parallel_agent.sh --cursor-model mini --claude-model haiku "Quick question"
```

### Options

| Option | Description |
|--------|-------------|
| `--json` | Output JSON for programmatic parsing |
| `--full-output` | Include complete agent outputs (no truncation) |
| `--validate` | Check outputs against success criteria |
| `--review <file>` | Code review mode |
| `--analyze <file>` | Bug/security analysis mode |
| `--improve <file>` | Improve observation YAML mode |
| `--cursor-only` | Run only Cursor Agent |
| `--gemini-only` | Run only Gemini CLI |
| `--claude-only` | Run only Claude CLI |
| `--no-claude` | Disable Claude CLI (enabled by default) |
| `--cursor-model <tier>` | Cursor model: mini, flash, advanced, auto (default: auto) |
| `--claude-model <tier>` | Claude model: haiku, sonnet, opus (default: sonnet) |
| `--check-credits` | Run pre-flight credit check |
| `--timeout <sec>` | Timeout per agent (default: 120) |
| `--output <dir>` | Custom output directory |

### Model Selection

The orchestrating agent selects models based on task complexity:

| Task Type | Cursor | Claude | Gemini | Reason |
|-----------|--------|--------|--------|--------|
| Security | advanced | opus | pro | Maximum capability for critical code |
| Review | flash | sonnet | flash | Balanced performance/cost |
| Analyze | flash | sonnet | flash | Good reasoning without opus cost |
| Improve | mini | haiku | flash | Lighter models for suggestions |
| Quick | mini | haiku | flash | Speed for simple queries |

**Model Tier Mappings:**

| Tier | Cursor | Claude | Gemini |
|------|--------|--------|--------|
| mini/haiku | gpt-5.1-codex-mini | haiku | - |
| flash/sonnet | gpt-5.1-codex | sonnet | gemini-3-flash-preview |
| advanced/opus/pro | gpt-5.2 | opus | gemini-3-pro-preview |

### Credit Exhaustion Fallback

The script automatically detects credit/quota exhaustion and falls back:

- **Cursor**: gpt-5.2 → gpt-5.1-codex → gpt-5.1-codex-mini → auto
- **Claude**: opus → sonnet → haiku

Detection methods:

1. Parse stderr for credit/quota error patterns after execution
2. Optional pre-flight check with `--check-credits` flag

### JSON Output Schema

```json
{
  "timestamp": "YYYYMMDD_HHMMSS",
  "mode": "review|analyze|prompt",
  "prompt": "The task description",
  "agents": {
    "cursor": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "model": "gpt-5.1-codex|auto",
      "credit_fallback": false,
      "output": "Agent response..."
    },
    "gemini": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "output": "Agent response..."
    },
    "claude": {
      "status": "complete|missing|failed",
      "validated": true|false,
      "model": "sonnet|haiku|opus",
      "credit_fallback": false,
      "output": "Agent response..."
    }
  },
  "output_files": {
    "cursor": "/path/to/cursor_output.txt",
    "gemini": "/path/to/gemini_output.txt",
    "claude": "/path/to/claude_output.txt",
    "summary": "/path/to/summary.md"
  },
  "cross_verification": {
    "consensus_score": 85,
    "confidence": "high|medium|low",
    "agent_count": 3
  }
}
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_INCLUDE_DIRS` | Colon-separated directories for Gemini | `$(pwd):~/.claude:~/.gemini` |
| `CURSOR_MODEL_MINI` | Model name for 'mini' tier | `gpt-5.1-codex-mini` |
| `CURSOR_MODEL_FLASH` | Model name for 'flash' tier | `gpt-5.1-codex` |
| `CURSOR_MODEL_ADVANCED` | Model name for 'advanced' tier | `gpt-5.2` |
| `GEMINI_MODEL_FLASH` | Model name for 'flash' tier | `gemini-3-flash-preview` |
| `GEMINI_MODEL_PRO` | Model name for 'pro' tier | `gemini-3-pro-preview` |
| `CHECK_CREDITS_PREFLIGHT` | Enable pre-flight credit check | `false` |

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

## Cross-Verification Patterns

### Pattern 1: Agreement Scoring

After receiving outputs from both agents, assess consensus:

```text
Consensus Score = (Agreements / Total_Findings) * 100

>=80%: High confidence - proceed with unified recommendation
50-79%: Medium confidence - highlight disagreements to user
<50%: Low confidence - escalate for human review
```

### Pattern 2: Synthesis

When agents disagree, synthesize by:

1. Identifying the core disagreement
2. Evaluating each agent's reasoning
3. Providing a unified recommendation with caveats
4. Noting which agent's approach was preferred and why

### Pattern 3: Specialization

Use agents for their strengths:

- **Gemini**: Broad knowledge, creative solutions, research
- **Cursor**: IDE-integrated context, code-specific analysis
- **Claude**: Deep reasoning, security analysis, complex logic

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
| Performance | 0.25 | No O(n^2), memory leaks |
| Maintainability | 0.25 | Clear naming, reasonable complexity |
| Test Coverage | 0.25 | Changes have corresponding tests |

---

## Workflow Integration

### Before Making Changes

```bash
# Get multi-agent review of proposed changes
~/.claude/scripts/parallel_agent.sh --json --validate \
  "Review this planned change: [description]. Files affected: [list]"
```

### After Making Changes

```bash
# Validate the implementation (use absolute path, 10 min timeout)
~/.claude/scripts/parallel_agent.sh --json --validate --timeout 600 --review /absolute/path/to/modified_file
```

### For Complex Decisions

```bash
# Get diverse perspectives
~/.claude/scripts/parallel_agent.sh --json --full-output \
  "Evaluate these approaches for [problem]: Option A: ... Option B: ..."
```

---

## Error Handling

The script implements:

- **Agent validation**: Checks if `cursor`, `gemini`, and `claude` commands exist
- **Retry logic**: Retries once after 5s delay on failure
- **Partial results**: Continues with available agent outputs if some fail
- **Credit fallback**: Automatically retries with cheaper models on quota errors
- **Exit codes**: 0=success, 1=no args, 2=no agents available

---

## Output Location

All outputs are stored in: `~/.claude/.agent_outputs/`

Files generated per run:

- `cursor_YYYYMMDD_HHMMSS.txt` - Cursor Agent output
- `gemini_YYYYMMDD_HHMMSS.txt` - Gemini CLI output
- `claude_YYYYMMDD_HHMMSS.txt` - Claude CLI output
- `summary_YYYYMMDD_HHMMSS.md` - Markdown summary
- `results_YYYYMMDD_HHMMSS.json` - JSON output (if --json)

---

## Orchestrated Code Review Workflow

When modifying code, the orchestrating agent spawns subagents for analysis, synthesis, and validation.

### Workflow Overview

```text
+---------------------------------------------------------------+
|                     Orchestrator                                |
+---------------------------------------------------------------+
|  1. Receive code modification task                              |
|  2. Pre-flight analysis                                         |
|  3. If criteria met -> Bash: parallel_agent.sh --json --validate|
|  4. Parse JSON output from agents                               |
|  5. If disagreement -> Synthesis                                |
|  6. Validation against criteria                                 |
|  7. Report final result to user                                 |
+---------------------------------------------------------------+
```

### Phase 1: Pre-flight Analysis

Before making significant code changes, determine if parallel review is needed by
analyzing files/changes against the criteria in `~/.claude/prompts/preflight_analysis.md`
(symlinked at `~/.gemini/prompts/preflight_analysis.md`).

Return JSON with `needs_parallel_review`, `reason`, `triggered_criteria`, `confidence`.

**Trigger Criteria**:

- Security-sensitive: auth, crypto, secrets, input validation
- Architectural: new services, API changes, schema modifications
- Large changes: >200 lines modified
- Critical logic: payments, user data, compliance

### Phase 2: Parallel Agent Review

If pre-flight triggers review, execute:

```bash
# Always use absolute paths and large timeout for file arguments
~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 600 --review /absolute/path/to/file
```

Parse the JSON output to extract:

- `agents.gemini.output` - Gemini's analysis
- `agents.cursor.output` - Cursor's analysis
- `agents.claude.output` - Claude's analysis
- `agents.*.status` - Agent completion status
- `cross_verification.consensus_score` - Agreement percentage

### Phase 3: Synthesis (on disagreement)

When agents disagree (consensus < 80%), synthesize using the template at
`~/.claude/prompts/synthesis.md` (symlinked at `~/.gemini/prompts/synthesis.md`).

Return JSON with `consensus_score`, `disagreements`, `unified_recommendation`.

**Consensus Thresholds**:

- >=80%: High confidence - proceed with unified recommendation
- 50-79%: Medium confidence - highlight disagreements to user
- <50%: Low confidence - escalate for human review

### Phase 4: Validation

Always run validation before finalizing changes using the criteria in
`~/.claude/prompts/validation.md` and `~/.claude/config/validation_criteria.yml`
(both symlinked into `~/.gemini/`).

Return JSON with `tier1` results, `tier2` results, `overall_verdict`.

**Verdicts**:

- `APPROVED`: All Tier 1 checks pass, Tier 2 score >= 0.60
- `NEEDS_REVIEW`: All Tier 1 checks pass, Tier 2 score < 0.60
- `BLOCKED`: Any Tier 1 check fails

### Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis prompt template |
| `~/.claude/prompts/synthesis.md` | Disagreement synthesis prompt template |
| `~/.claude/prompts/validation.md` | Validation criteria prompt template |
| `~/.claude/config/validation_criteria.yml` | Detailed validation rules and thresholds |

All of the above are accessible via symlinks under `~/.gemini/prompts/` and
`~/.gemini/config/`.

### Example Orchestration Flow

```text
User: "Add authentication middleware to the API routes"

Orchestrator:
  1. Pre-flight analysis
     -> Returns: {needs_parallel_review: true, reason: "Authentication logic", confidence: 0.95}

  2. Executes: ~/.claude/scripts/parallel_agent.sh --json --validate --timeout 600 \
       --cursor-model advanced --claude-model opus --review "$(pwd)/src/middleware/auth.js"
     -> Gemini: "Use JWT with refresh tokens, add rate limiting"
     -> Cursor: "Use JWT with session fallback, add CSRF protection"
     -> Claude: "Use JWT with refresh tokens, add rate limiting and input validation"
     -> Consensus: 75% (MEDIUM)

  3. Synthesis
     -> Returns: {consensus_score: 0.75, unified_recommendation: "Use JWT with refresh tokens, add rate limiting, CSRF, and input validation"}

  4. Validation
     -> Returns: {tier1: {passed: true}, tier2: {score: 0.85}, verdict: "APPROVED"}

  5. Reports to user with synthesized recommendation and validation results
```

---

## Native Commands

Gemini CLI slash commands are defined as TOML files in `~/.gemini/commands/`.
These integrate with the parallel agent orchestration framework.

### Available Commands

| Command | File | Description | Parallel Agents |
|---------|------|-------------|-----------------|
| `/project-commit` | `project-commit.toml` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/refactor-python` | `refactor-python.toml` | Python codebase security and quality analysis | ALWAYS |
| `/refactor-shell` | `refactor-shell.toml` | Bash/Shell script security and quality analysis | ALWAYS |
| `/docs-readme` | `docs-readme.toml` | Improve README documentation | NO |
| `/docs-diagrams` | `docs-diagrams.toml` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | `docs-improve.toml` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/plan-manage` | `plan-manage.toml` | Plan lifecycle with parallel agent orchestration for create/review | CONDITIONAL |
| `/checkpoint` | `checkpoint.toml` | Save context checkpoint for session continuity | NO |

### Command Usage

Commands are TOML-based slash commands invoked in Gemini CLI:

```bash
# Full commit pipeline with documentation generation
/project-commit "Add new feature"
/project-commit  # Auto-generate commit message

# Comprehensive Python refactoring analysis
/refactor-python src/

# Shell script security and quality analysis
/refactor-shell scripts/

# Generate architecture diagrams
/docs-diagrams docs/ARCHITECTURE_DIAGRAMS.md

# Improve README documentation
/docs-readme

# Analyze documentation against Diataxis framework
/docs-improve docs/

# Manage implementation plans
/plan-manage

# Save a context checkpoint
/checkpoint
```

### Auto-Triggered Skill

The `code-quality` skill (symlinked from `~/.claude/skills/code-quality/SKILL.md`)
auto-triggers when detecting:

1. **Security patterns**: auth, crypto, secrets, input validation
2. **Complexity patterns**:
   - File > 500 lines
   - > 10 functions per file
   - > 5 classes per file

When triggered, it provides inline feedback without blocking user workflow.

---

## Configuration Files

All configuration is symlinked from `~/.claude/` to ensure both Claude and Gemini
operate from identical orchestration rules.

| File | Purpose |
|------|---------|
| `~/.claude/config/command_config.yml` | Thresholds, tool policies, error recovery |
| `~/.claude/config/validation_criteria.yml` | Tier 1/Tier 2 validation rules with command overrides |
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis template |
| `~/.claude/prompts/synthesis.md` | Agent disagreement synthesis template |
| `~/.claude/prompts/validation.md` | Validation criteria template |

> Accessible locally via `~/.gemini/config/` and `~/.gemini/prompts/` symlinks.

---

## File Structure

```text
~/.gemini/
├── GEMINI.md                        # This orchestration guide
├── commands/                        # TOML slash commands
│   ├── project-commit.toml
│   ├── refactor-python.toml
│   ├── refactor-shell.toml
│   ├── docs-diagrams.toml
│   ├── docs-improve.toml
│   ├── docs-readme.toml
│   ├── plan-manage.toml
│   └── checkpoint.toml
├── skills/
│   └── code-quality/
│       └── SKILL.md                 # Symlinked from ~/.claude/skills/
├── prompts/ -> ~/.claude/prompts/   # Symlinked shared templates
├── config/ -> ~/.claude/config/     # Symlinked shared configs
├── scripts/ -> ~/.claude/scripts/   # Symlinked shared scripts
├── .plans/ -> ~/.claude/.plans/     # Symlinked shared plans
└── settings.json                    # Gemini CLI project settings
```

> **Note**: The `skills/` directory exists only in the deployed `~/.gemini/` location
> (created by `bootstrap.sh`), NOT in the repository's `.gemini/` directory.
> This prevents skill conflict warnings when Gemini runs inside the Manifest repo.

---

## Plan Management

Implementation plans are tracked as markdown files in `~/.claude/.plans/`
(symlinked at `~/.gemini/.plans/`).

### Lifecycle

```text
CREATE -> ACTIVE -> COMPLETED (.archive/) or ABANDONED (.abandoned/)
```

1. **CREATE**: Copy `TEMPLATE.md`, save as `YYYYMMDD-short-description.md`
2. **ACTIVE**: Plan lives in `.plans/` root while work is in progress; check off deliverables as they are completed
3. **COMPLETED**: Move to `.archive/` when all deliverables are done
4. **ABANDONED**: Move to `.abandoned/` if superseded or no longer relevant

### Housekeeping Rules

- **Before creating a plan**: Review existing plans in `.plans/` to avoid duplicates
- **During implementation**: Check off deliverables (`- [x]`) as each is completed
- **Staleness threshold**: Plans untouched for 7+ days should be reviewed -- either update, complete, or abandon them
- **Use `/plan-manage`** for orchestrated plan creation (parallel agents for cross-verified
  planning), review, archiving, and abandoning plans
