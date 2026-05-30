# Orchestration Reference

> Multi-agent review workflow, cross-verification patterns, synthesis, and
> validation phases. Referenced from CLAUDE.md.

## Cross-Verification Patterns

### Pattern 1: Agreement Scoring

After receiving outputs from both agents, assess consensus:

```text
Consensus Score = (Agreements / Total_Findings) * 100

≥80%: High confidence - proceed with unified recommendation
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

## Error Handling

The script implements:

- **Agent validation**: Checks if `cursor`, `gemini`, and `claude` commands exist
- **Retry logic**: Retries once after 5s delay on failure
- **Partial results**: Continues with available agent outputs if some fail
- **Credit fallback**: Automatically retries with cheaper models on quota errors
- **Exit codes**: 0=success, 1=no args, 2=no agents available

## Orchestrated Code Review Workflow

When modifying code, Claude acts as an orchestrator that spawns Task subagents for analysis, synthesis, and validation.

### Workflow Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Claude (Orchestrator)                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Receive code modification task                               │
│  2. Task(Explore) → Pre-flight analysis                          │
│  3. If criteria met → Bash: parallel_agent.sh --json --validate  │
│  4. Parse JSON output from agents                                │
│  5. If disagreement → Task(general-purpose) → Synthesis          │
│  6. Task(general-purpose) → Validation against criteria          │
│  7. Report final result to user                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 1: Pre-flight Analysis

Before making significant code changes, spawn a Task agent to determine if parallel review is needed:

```text
Task(
  subagent_type: "Explore",
  prompt: "Analyze these files/changes against the criteria in ~/.claude/prompts/preflight_analysis.md:
           [FILES_OR_DIFF]
           Return JSON with needs_parallel_review, reason, triggered_criteria, confidence"
)
```

**Trigger Criteria** (from `~/.claude/prompts/preflight_analysis.md`):

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

When agents disagree (consensus < 80%), spawn a synthesis agent:

```text
Task(
  subagent_type: "general-purpose",
  prompt: "Using the template at ~/.claude/prompts/synthesis.md, synthesize these outputs:
           Original task: [TASK]
           Gemini output: [GEMINI_OUTPUT]
           Cursor output: [CURSOR_OUTPUT]
           Claude output: [CLAUDE_OUTPUT]
           Return JSON with consensus_score, disagreements, unified_recommendation"
)
```

**Consensus Thresholds**:

- ≥80%: High confidence - proceed with unified recommendation
- 50-79%: Medium confidence - highlight disagreements to user
- <50%: Low confidence - escalate for human review

### Phase 4: Validation

Always run validation before finalizing changes:

```text
Task(
  subagent_type: "general-purpose",
  prompt: "Using the criteria in ~/.claude/prompts/validation.md and ~/.claude/config/validation_criteria.yml,
           validate this code: [CODE_OR_DIFF]
           Return JSON with tier1 results, tier2 results, overall_verdict"
)
```

**Verdicts**:

- `APPROVED`: All Tier 1 checks pass, Tier 2 score ≥ 0.60
- `NEEDS_REVIEW`: All Tier 1 checks pass, Tier 2 score < 0.60
- `BLOCKED`: Any Tier 1 check fails

### Configuration Files

| File | Purpose |
|------|---------|
| `~/.claude/prompts/preflight_analysis.md` | Pre-flight analysis prompt template |
| `~/.claude/prompts/synthesis.md` | Disagreement synthesis prompt template |
| `~/.claude/prompts/validation.md` | Validation criteria prompt template |
| `~/.claude/config/validation_criteria.yml` | Detailed validation rules and thresholds |

### Example Orchestration Flow

```text
User: "Add authentication middleware to the API routes"

Claude (Orchestrator):
  1. Spawns Task(Explore) for pre-flight analysis
     → Returns: {needs_parallel_review: true, reason: "Authentication logic", confidence: 0.95}

  2. Executes: ~/.claude/scripts/parallel_agent.sh --json --validate --timeout 600 \
       --cursor-model advanced --claude-model opus --review "$(pwd)/src/middleware/auth.js"
     → Gemini: "Use JWT with refresh tokens, add rate limiting"
     → Cursor: "Use JWT with session fallback, add CSRF protection"
     → Claude: "Use JWT with refresh tokens, add rate limiting and input validation"
     → Consensus: 75% (MEDIUM)

  3. Spawns Task(general-purpose) for synthesis
     → Returns: {consensus_score: 0.75, unified_recommendation: "Use JWT with refresh tokens, add rate limiting, CSRF, and input validation"}

  4. Spawns Task(general-purpose) for validation
     → Returns: {tier1: {passed: true}, tier2: {score: 0.85}, verdict: "APPROVED"}

  5. Reports to user with synthesized recommendation and validation results
```
