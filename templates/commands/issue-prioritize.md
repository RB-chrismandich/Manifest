# Role: Issue Prioritization Analyst

## Objective

Fetch open GitHub issues, analyze them against the project's current state and architecture, and recommend the top 5 issues to address next — ranked by impact, urgency, and implementation readiness.

---

## Customization Required

Before using this command, customize the following sections for your project:

### Project Context (Required)

Replace the placeholders with your project's architecture and component map:

```markdown
**Architecture**: [Your architecture pattern]
**Languages**: [Languages used]
**Infrastructure**: [Key infrastructure]

### Component/Service Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| [Name] | [Lang] | [Brief description] |
```

### Prioritization Weights (Optional)

The default scoring formula is:
```
Priority Score = (Impact * 3) + (Urgency * 2) + (Readiness * 2) - (Risk * 1)
```

Adjust based on your project phase:
- **Early stage** (MVP): Increase Urgency weight, reduce Risk penalty
- **Growth stage**: Balance all factors
- **Mature stage**: Increase Risk weight, prioritize stability

### Project Phase Context (Optional)

Consider your current project phase when scoring:
- **Phase 1 (MVP)**: Prioritize core features over nice-to-haves
- **Phase 2 (Growth)**: Balance features with stability
- **Phase 3 (Scale)**: Prioritize performance and observability
- **Phase 4 (Production)**: Prioritize stability, security, observability over new features

---

## Workflow

### Step 1: Fetch Open Issues

```bash
gh issue list --state open --limit 500 --json number,title,labels,createdAt,updatedAt,body -R {owner}/{repo}
```

**Replace `{owner}/{repo}` with your repository.**

**Filter out issues with the `processed` label** before analysis. These have already been triaged and implemented.

If there are fewer than 5 remaining open issues, note this and rank all of them.

### Step 2: Categorize Each Issue

For each open issue, classify it along these dimensions:

**Type**:
- `bug` — Something is broken or incorrect
- `feature` — New functionality
- `enhancement` — Improvement to existing functionality
- `test` — Missing test coverage
- `tech-debt` — Refactoring, cleanup, dependency updates
- `docs` — Documentation improvements
- `infra` — Infrastructure, CI/CD, deployment

**Impact** (1-5):
- 5: Blocks core functionality or causes data loss
- 4: Affects user-facing features significantly
- 3: Improves reliability, performance, or developer experience
- 2: Nice-to-have improvement
- 1: Cosmetic or minor

**Urgency** (1-5):
- 5: Actively causing problems in production
- 4: Will cause problems soon or blocks other work
- 3: Should be done this sprint
- 2: Can wait but shouldn't be forgotten
- 1: Backlog — do when convenient

**Readiness** (1-5):
- 5: Well-defined, has an implementation plan, can start immediately
- 4: Clear requirements, needs minor investigation
- 3: Requirements known but needs design work
- 2: Needs significant exploration or discussion
- 1: Vague, needs requirements gathering

**Risk** (1-5, lower is better):
- 1: Isolated change, low risk of breakage
- 2: Touches one component, moderate testing needed
- 3: Cross-component change, careful coordination needed
- 4: Architectural change, significant testing needed
- 5: High-risk change to critical path (data integrity, auth, payments)

### Step 3: Score and Rank

**Priority Score** = (Impact * 3) + (Urgency * 2) + (Readiness * 2) - (Risk * 1)

Higher score = higher priority.

In case of ties, prefer:
1. Bugs over features
2. Issues that unblock other issues
3. Issues with implementation plans (`planned` label)
4. Older issues over newer ones

### Step 4: Explore Context for Top Candidates

For the top 5-7 candidates, briefly check the codebase to validate:
- Are the referenced files/components still in the expected state?
- Does the issue duplicate or overlap with recent commits?
- Is there an existing implementation plan in the issue comments?

**Use Task sub-agents** for efficient parallel exploration:
```
Task(subagent_type: "Explore", prompt: "Check if issue #NNN is still relevant...")
```

### Step 5: Present Results

Format the output as:

```markdown
# Issue Prioritization Report

**Generated**: [date]
**Open Issues Analyzed**: [count]
**Project Phase**: [phase if specified]

## Top 5 Recommended Issues

### 1. #[number] — [title]
- **Type**: [type] | **Score**: [score]
- **Impact**: [1-5] | **Urgency**: [1-5] | **Readiness**: [1-5] | **Risk**: [1-5]
- **Components**: [affected components]
- **Rationale**: [1-2 sentences on why this ranks here]
- **Has Plan**: Yes/No
- **Dependencies**: [issues this blocks or is blocked by, if any]

[Repeat for issues 2-5]

## Scoring Summary

| Rank | Issue | Type | Impact | Urgency | Readiness | Risk | Score |
|------|-------|------|--------|---------|-----------|------|-------|
| 1 | #NNN | ... | ... | ... | ... | ... | ... |
| 2 | #NNN | ... | ... | ... | ... | ... | ... |
| 3 | #NNN | ... | ... | ... | ... | ... | ... |
| 4 | #NNN | ... | ... | ... | ... | ... | ... |
| 5 | #NNN | ... | ... | ... | ... | ... | ... |

## Honorable Mentions

[2-3 issues that almost made the top 5, with brief reasoning]

## Observations

[Any patterns noticed — e.g., "many issues are blocked on [dependency]",
"several issues overlap and could be batched", "test coverage issues are accumulating"]
```

### Step 6: STOP

Report the prioritized list to the user. Do not begin implementing any issues.

---

## Critical Rules

1. **Do not implement anything.** This command is analysis-only.
2. **Do not modify any files** in the repository (except this command's output to the terminal).
3. **Score objectively.** Do not inflate scores based on how interesting an issue is.
4. **Consider dependencies.** An issue that unblocks 3 others is more valuable than an isolated improvement.
5. **Account for the project phase.** Prioritize accordingly (see Customization section).
6. **Flag stale issues.** If an issue references code/files that no longer exist, note it as potentially stale.

---

## Integration with Parallel Agents

For complex scoring decisions, use parallel agents:

```bash
~/.claude/scripts/parallel_agent.sh --json --timeout 300 \
  "Score this issue for a [project phase] project: [issue summary].
   Rate Impact (1-5), Urgency (1-5), Readiness (1-5), Risk (1-5)."
```

Use consensus across agents to validate your scoring:
- >= 80% agreement: Confident in score
- 50-79% agreement: Note scoring variance in report
- < 50% agreement: Escalate issue for human review

---

## Example Usage

```bash
# Prioritize all open issues
/issue-prioritize

# Analyze with project phase context
# (Customize the command to accept phase argument if needed)
/issue-prioritize --phase production-readiness
```

---

## Customization Notes

**For multi-repo projects**: Modify Step 1 to fetch issues from multiple repositories and aggregate them.

**For label-based filtering**: Add filtering logic in Step 1 to exclude certain labels (e.g., `wontfix`, `on-hold`).

**For milestone integration**: Include milestone information in the report to show how top issues align with upcoming releases.
