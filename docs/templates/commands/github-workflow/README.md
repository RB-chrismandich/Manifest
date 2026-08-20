# GitHub Issue Workflow Commands

> Complete issue management lifecycle: triage → prioritize → plan → process → review

**Purpose**: Provide production-grade commands for managing GitHub issues at scale, from backlog cleanup through implementation and validation.

---

## Overview

These commands form a complete issue management workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│                      GitHub Issue Lifecycle                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. TRIAGE (issue-triage)                                       │
│     └─> Clean backlog, find duplicates, validate priorities     │
│                                                                  │
│  2. PRIORITIZE (issue-prioritize)                               │
│     └─> Score and rank issues by impact/urgency/readiness       │
│                                                                  │
│  3. PLAN (issue-plan)                                           │
│     └─> Generate detailed implementation plan, post to issue    │
│                                                                  │
│  4. PROCESS (issue-process)                                     │
│     └─> Implement, test, validate, commit, create follow-ups    │
│                                                                  │
│  5. REVIEW (issue-review)                                       │
│     └─> Audit processed issues, close complete, flag incomplete │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Command Descriptions

| Command | Purpose | Typical Frequency | Duration |
|---------|---------|------------------|----------|
| `issue-triage` | Clean up backlog, identify duplicates/stale issues | Weekly | 15-30 min |
| `issue-prioritize` | Rank top 5 issues to work on next | Weekly | 5-10 min |
| `issue-plan` | Create implementation plan for a specific issue | Per issue | 10-20 min |
| `issue-process` | Implement, test, and validate an issue end-to-end | Per issue | 30-120 min |
| `issue-review` | Audit processed issues, close complete ones | Daily/Weekly | 5-15 min |

---

## Setup

### 1. Copy Commands to Your Project

```bash
# Copy all workflow commands
cp templates/commands/github-workflow/*.md .claude/commands/

# Or copy individually
cp templates/commands/issue-triage.md .claude/commands/
cp templates/commands/issue-prioritize.md .claude/commands/
cp templates/commands/issue-plan.md .claude/commands/
cp templates/commands/issue-process.md .claude/commands/
cp templates/commands/issue-review.md .claude/commands/
```

### 2. Customize Each Command

Each command has a **"Customization Required"** section at the top. You must customize:

#### Project Context (All Commands)

Replace placeholders with your actual project details:

```markdown
**Architecture**: [Your architecture pattern]
**Languages**: [Languages used]
**Infrastructure**: [Key infrastructure]

### Component/Service Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| [Name] | [Lang] | [Brief description] |
```

#### Repository Path (All Commands)

Find and replace `{owner}/{repo}` with your actual GitHub repository path (e.g., `facebook/react`).

#### Prioritization Weights (Optional)

Adjust scoring formulas based on your project phase:

- **Early stage**: Increase Urgency weight
- **Growth stage**: Balance all factors
- **Mature stage**: Increase Risk weight

#### Test Commands (issue-process)

Define your project's test commands:

```bash
# Unit tests
make test
# OR npm test, pytest, etc.

# Integration tests
make test-integration

# Lint
make lint
```

### 3. Create Required Labels

These commands use specific GitHub labels:

```bash
# Create all required labels at once
gh label create "planned" --description "Implementation plan posted" --color "1D76DB" -R {owner}/{repo}
gh label create "processed" --description "Fully implemented and validated" --color "0E8A16" -R {owner}/{repo}
gh label create "needs-review" --description "Requires human review" --color "FBCA04" -R {owner}/{repo}
gh label create "follow-up" --description "Follow-up from processed issue" --color "D4C5F9" -R {owner}/{repo}
```

---

## Usage Guide

### Typical Weekly Workflow

```bash
# Monday: Clean backlog
/issue-triage --dry-run          # Review recommendations
/issue-triage                     # Apply changes

# Monday: Prioritize work
/issue-prioritize                 # Get top 5 issues

# During week: Plan & implement
/issue-plan 123                   # Generate plan
/issue-process 123                # Implement it

# Friday: Review progress
/issue-review                     # Audit all processed issues
```

### Common Scenarios

#### Scenario 1: New sprint starting

```bash
# 1. Clean up last sprint's issues
/issue-review

# 2. Prioritize for new sprint
/issue-prioritize

# 3. Plan the top issues
/issue-plan <TOP_ISSUE_NUMBER>
/issue-plan <SECOND_TOP_ISSUE_NUMBER>
```

#### Scenario 2: Large backlog cleanup

```bash
# 1. Dry-run to see what would change
/issue-triage --dry-run

# 2. Review recommendations, then apply
/issue-triage

# 3. Close stale issues (be careful!)
/issue-triage --close-stale
```

#### Scenario 3: Single issue workflow

```bash
# 1. Plan it
/issue-plan 456

# 2. Review the plan in the GitHub issue
# (Go to the issue, read the plan, approve it)

# 3. Implement it
/issue-process 456

# 4. If status is "processed", it's ready to merge
# If status is "needs-review", human review required
```

---

## Command Details

### issue-triage

**Purpose**: Comprehensive backlog audit

**What it does**:

- Detects duplicate issues (title/content similarity)
- Finds stale issues (references deleted files, inactive >90 days)
- Identifies overlapping issues (could be batched)
- Validates prioritization (label consistency)
- Generates actionable recommendations

**Arguments**:

- No args: Audit all open issues
- `--dry-run`: Report only, no actions
- `--close-stale`: Auto-close stale issues with high confidence
- `123, 456, 789`: Audit specific issue numbers only

**Safety**: Conservative closures (high confidence only), never modifies issue content, never closes `planned` issues.

**Output**: Comprehensive report with duplicates, stale issues, overlaps, prioritization issues, and actions taken.

---

### issue-prioritize

**Purpose**: Rank top 5 issues to work on next

**What it does**:

- Scores each issue: `(Impact * 3) + (Urgency * 2) + (Readiness * 2) - (Risk * 1)`
- Ranks by score (tiebreaker: bugs > features, older > newer)
- Validates issue relevance against current codebase
- Identifies issues that unblock others

**Arguments**:

- No args: Analyze all open issues

**Output**: Top 5 recommended issues with scores, rationale, and scoring table. Honorable mentions for #6-8.

**Note**: Analysis-only. Does not modify anything.

---

### issue-plan

**Purpose**: Generate detailed implementation plan

**What it does**:

- Explores the codebase (read-only)
- Identifies affected components
- Designs implementation approach
- Lists specific file changes, migrations, schema updates
- Validates plan with parallel agents
- Posts plan to GitHub issue
- Adds `planned` label

**Arguments**:

- `123`: Issue number
- `https://github.com/owner/repo/issues/456`: Issue URL

**Safety**: Planning-only. NEVER writes code or modifies repository files.

**Output**: Detailed plan posted to issue (replaces body if empty, adds comment if body exists).

**Parallel Agent Integration**: Validates plan with `~/.claude/scripts/parallel_agent.py` for consensus scoring.

---

### issue-process

**Purpose**: Implement, test, and validate an issue end-to-end

**What it does**:

- Requires `planned` label (gates implementation)
- Extracts checklists from issue body and comments
- Follows implementation plan from issue
- Delegates to Task sub-agents per component
- Runs unit/integration tests and linting
- Validates with parallel agents (consensus scoring)
- Updates checklists in issue body/comments
- Posts implementation update comment
- Creates follow-up issues for partial/blocked items
- Commits changes (if status is "processed")
- Applies `processed` or `needs-review` label

**Arguments**:

- `123`: Issue number
- `https://github.com/owner/repo/issues/456`: Issue URL

**Safety**: Requires plan gate. Respects architectural constraints. Commits only if fully validated.

**Output**: Implementation comment on issue, follow-up issues created, commit (if status=processed).

**Parallel Agent Integration**: Validates each modified file with consensus scoring.

---

### issue-review

**Purpose**: Audit processed issues, close complete ones

**What it does**:

- Fetches all open issues with `processed` label
- Extracts checklists from body and comments
- Determines verdict: CLOSE (all checked or no checklist) vs. NEEDS-REVIEW (unchecked items)
- Detects follow-up items from implementation comments
- Creates missing follow-up issues (idempotent)
- Closes complete issues
- Adds `needs-review` label to incomplete issues

**Arguments**:

- No args: Audit all open processed issues
- `123`: Audit specific issue only

**Safety**: Conservative (flags ambiguous as needs-review). Maintains idempotency (won't create duplicate follow-ups).

**Output**: Audit report table with checklist status, follow-up issues, and actions taken.

---

## State Machine Flow

Issues progress through labeled states:

```
[no label]
    ↓
  [issue-triage validates/cleans backlog]
    ↓
[prioritized via issue-prioritize]
    ↓
  [issue-plan generates plan]
    ↓
[planned]
    ↓
  [issue-process implements]
    ↓
[processed] OR [needs-review]
    ↓
  [issue-review audits]
    ↓
[closed] OR [needs-review + follow-ups]
```

**Labels Used**:

- `planned` — Has implementation plan
- `processed` — Fully implemented, all tests pass, high consensus
- `needs-review` — Implemented but requires human review
- `follow-up` — Created as follow-up from processed issue

---

## Integration with Parallel Agents

All commands integrate with `~/.claude/scripts/parallel_agent.py` for cross-verification:

| Command | Use Case | Consensus Threshold |
|---------|----------|---------------------|
| `issue-triage` | Duplicate detection | >= 80% = HIGH confidence to close |
| `issue-prioritize` | Scoring validation | >= 80% = confident in score |
| `issue-plan` | Plan validation | >= 80% = HIGH confidence, 50-79% = MEDIUM (note disagreements), < 50% = LOW (add warning) |
| `issue-process` | Code validation | >= 80% = status "processed", 50-79% = status "needs-review" |

**Setup**: Ensure `~/.claude/scripts/parallel_agent.py` is installed and configured. See [README.md](../../README.md) for setup instructions.

---

## Customization Examples

### Example 1: Django Monolith

```markdown
**Architecture**: Django Monolith with Celery workers
**Languages**: Python 3.11
**Infrastructure**: PostgreSQL, Redis, Docker

### Component Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| Web | Python | Django views, templates, forms |
| API | Python | Django REST Framework endpoints |
| Tasks | Python | Celery background tasks |
| Admin | Python | Django admin customizations |

### Key Constraints

- All database access via Django ORM
- No direct SQL except in migrations
- Celery tasks must be idempotent
- API changes must include OpenAPI schema updates
```

### Example 2: Microservices (Go + Node.js)

```markdown
**Architecture**: Event-Driven Microservices
**Languages**: Go, Node.js
**Infrastructure**: Kubernetes, PostgreSQL (per-service), RabbitMQ

### Component Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| Auth | Go | Authentication, JWT tokens |
| Users | Go | User profile management |
| Orders | Node.js | Order processing, gRPC API |
| Notifications | Node.js | Event-driven notification consumer |

### Key Constraints

- No cross-schema database access (services communicate via RabbitMQ)
- All events use Protocol Buffers with correlation_id
- Deploy publisher before consumer for new event types
- gRPC updates use optimistic locking
```

### Example 3: Frontend (React)

```markdown
**Architecture**: React SPA with GraphQL API
**Languages**: TypeScript
**Infrastructure**: Next.js, Apollo Client, GraphQL

### Component Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| Components | TypeScript | Reusable UI components |
| Pages | TypeScript | Next.js page routes |
| Hooks | TypeScript | Custom React hooks |
| GraphQL | TypeScript | Apollo Client queries/mutations |

### Key Constraints

- All components must have Storybook stories
- GraphQL queries must use fragments for reusability
- All API calls via Apollo Client (no fetch)
- Accessibility: WCAG 2.1 AA compliance required
```

---

## Best Practices

### 1. Run Triage Before Prioritize

Clean backlog first (remove duplicates/stale) before prioritizing:

```bash
/issue-triage --dry-run    # Review
/issue-triage              # Apply
/issue-prioritize          # Then prioritize clean backlog
```

### 2. Always Plan Before Processing

Never skip the planning phase:

```bash
# BAD
/issue-process 123   # Will fail: no plan exists

# GOOD
/issue-plan 123      # Generate plan
# Review plan in GitHub issue
/issue-process 123   # Implement
```

### 3. Review Processed Issues Regularly

Don't let processed issues accumulate:

```bash
# Daily or weekly
/issue-review
```

This closes complete issues and creates follow-ups for incomplete work.

### 4. Use Dry-Run for Triage

Always dry-run triage before applying changes to production backlog:

```bash
/issue-triage --dry-run    # Review what would change
# Review recommendations carefully
/issue-triage              # Apply if confident
```

### 5. Validate Parallel Agent Output

When commands use parallel agents, check consensus scores:

- **>= 80%**: High confidence, trust the output
- **50-79%**: Medium confidence, review disagreements
- **< 50%**: Low confidence, escalate for human review

### 6. Customize Scoring for Your Project Phase

Adjust prioritization weights in `issue-prioritize`:

- **Early stage (MVP)**: `(Impact * 4) + (Urgency * 3) + (Readiness * 2) - (Risk * 0.5)`
- **Growth stage**: Use default weights
- **Mature (Production)**: `(Impact * 2) + (Urgency * 1) + (Readiness * 2) - (Risk * 3)`

---

## Troubleshooting

### Issue: Command not found

**Symptom**: `/issue-triage` returns "Command not found"

**Solution**: Copy the command file to `.claude/commands/`:

```bash
cp templates/commands/issue-triage.md .claude/commands/
```

### Issue: Parallel agent script not found

**Symptom**: Commands report "parallel_agent.py not available"

**Solution**: Install the parallel agent script:

```bash
cp .claude/scripts/parallel_agent.py ~/.claude/scripts/
chmod +x ~/.claude/scripts/parallel_agent.py
```

### Issue: GitHub CLI not authenticated

**Symptom**: `gh` commands fail with "authentication required"

**Solution**: Authenticate GitHub CLI:

```bash
gh auth login
```

### Issue: issue-process fails at plan gate

**Symptom**: "This issue has not been planned yet"

**Solution**: Run `/issue-plan` first to generate the plan, then retry `/issue-process`.

### Issue: Too many follow-up issues created

**Symptom**: Dozens of follow-up issues from a single parent

**Solution**: This is usually correct behavior (partial implementations create many follow-ups). Review the parent issue's implementation comment to see why items were partial/blocked.

To prevent: Break large issues into smaller ones before processing.

### Issue: Prioritization scores seem wrong

**Symptom**: Low-priority issues ranked higher than critical bugs

**Solution**:

1. Review the scoring formula in `issue-prioritize`
2. Adjust weights for your project phase
3. Manually override scores by adding/removing labels

---

## Advanced Usage

### Multi-Repo Workflows

To triage across multiple repositories:

```bash
# Triage each repo
/issue-triage --repo owner/repo1
/issue-triage --repo owner/repo2

# Aggregate priorities
/issue-prioritize --repos owner/repo1,owner/repo2
```

**Note**: Requires customization of commands to accept `--repo` arguments.

### Batch Processing

Process multiple issues in one command:

```bash
/issue-process 123 456 789
```

**Note**: Requires customization to loop over arguments.

### CI/CD Integration

Run issue-review as a CI job:

```yaml
# .github/workflows/issue-audit.yml
name: Issue Audit
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9am
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: |
          claude run "/issue-review" > audit-report.md
          gh issue comment <TRACKING_ISSUE> --body-file audit-report.md
```

---

## Related Documentation

- [Command State Machine Pattern](../../patterns/command-state-machine.md) - Error recovery, validation patterns
- [Full Deployment Pipeline Example](../full-deployment-pipeline.md) - Multi-phase command example
- [COMMANDS.md](../../../COMMANDS.md) - General command documentation
- [Parallel Agent Guide](../../../../configs/claude/CLAUDE.md) - Parallel agent orchestration

---

## Contributing

To contribute new workflow commands or improvements:

1. Follow the command template structure
2. Include "Customization Required" section
3. Add parallel agent integration points
4. Document safety guarantees
5. Test with real issues before submitting PR

---

## License

Same as Manifest project (see root LICENSE file)
