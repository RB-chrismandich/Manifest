# Role: Issue Triage & Cleanup Agent

## Objective

Perform a comprehensive audit of all open GitHub issues: validate prioritization, identify duplicates and overlapping issues, consolidate where appropriate, close stale or obsolete issues, and produce a clean, actionable issue backlog.

**Arguments (optional)**: $ARGUMENTS

If arguments are provided, they may specify:
- A comma-separated list of issue numbers to audit (e.g., `271, 272, 274`)
- `--dry-run` — analyze and report only, take no actions
- `--close-stale` — auto-close issues that reference deleted files or completed work
- No arguments = audit all open issues

---

## Customization Required

Before using this command, customize the following sections for your project:

### Project Context (Required)

Replace the placeholders with your project's architecture and service map:

```markdown
**Architecture**: [Your architecture pattern, e.g., Microservices, Monolith, Event-Driven]
**Languages**: [Languages used in your project]
**Infrastructure**: [Key infrastructure components]

### Service/Component Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| [Name] | [Lang] | [Brief description] |
```

**Tip**: If you don't have services, list major modules, packages, or functional areas instead.

### Prioritization Scoring (Optional)

The default scoring formula is:
```
Priority Score = (Impact * 3) + (Urgency * 2) + (Readiness * 2) - (Risk * 1)
```

Adjust the weights if your project has different priorities (e.g., prioritize risk reduction over readiness).

---

## Workflow

### Step 1: Fetch All Open Issues

```bash
gh issue list --state open --limit 500 --json number,title,labels,createdAt,updatedAt,body,assignees -R {owner}/{repo}
```

**Replace `{owner}/{repo}` with your repository.**

Parse arguments to determine scope:
- If specific issue numbers provided, filter to those
- If `--dry-run` flag present, set `DRY_RUN=true` (report only, no mutations)
- If `--close-stale` flag present, set `CLOSE_STALE=true`
- Default: audit all open issues, take actions, but do NOT close stale issues without `--close-stale`

### Step 2: Classify and Group Issues

For each issue, extract:
- **Number, title, labels, body** (from API response)
- **Age** (days since creation)
- **Last activity** (days since last update)
- **Components mentioned** (parse body for component/service names, file paths)
- **Category**: bug, feature, enhancement, test, tech-debt, docs, infra, follow-up, chore

Group issues by:
1. **Component/area** (which component or cross-cutting concern)
2. **Topic cluster** (semantically related issues)
3. **Label** (planned, processed, follow-up, enhancement, bug, etc.)

### Step 3: Detect Duplicates and Overlaps

Compare every pair of issues for similarity. Flag pairs as:

**Duplicate** (same problem/feature described differently):
- Title similarity > 80% (fuzzy match)
- Body references same files AND same acceptance criteria
- One issue is a subset of another

**Overlapping** (related but distinct, could be batched):
- Same component + same area of concern
- Acceptance criteria partially overlap
- One issue's follow-up items match another issue's scope

**Parent-Child** (one issue was created as follow-up of another):
- Body contains `<!-- follow-up-from: #NNN -->` or `Follow-up from #NNN`
- Labels include `follow-up`

For each flagged pair, record:
- Issue numbers
- Relationship type (duplicate / overlapping / parent-child)
- Confidence (high / medium / low)
- Recommended action (merge, close-as-dup, batch, link, none)

### Step 4: Detect Stale Issues

An issue is **stale** if ANY of:
- References files that no longer exist in the codebase (verify with `ls` or `test -f`)
- Describes a problem that has already been fixed (check recent commits or current code state)
- Has not been updated in > 90 days AND has no `planned` label
- References a component that has been removed or deprecated
- Acceptance criteria are already satisfied by current codebase state

**Customization**: Adjust the 90-day threshold based on your project's velocity.

For each stale issue, record:
- Issue number
- Staleness reason
- Confidence (high / medium / low)
- Recommended action (close / update / investigate)

### Step 5: Validate Prioritization

Score each non-stale issue using the prioritization framework:

**Priority Score** = (Impact * 3) + (Urgency * 2) + (Readiness * 2) - (Risk * 1)

Where:
- **Impact** (1-5): How much does this affect users or system reliability?
- **Urgency** (1-5): How soon does this need to happen?
- **Readiness** (1-5): How well-defined is the issue? Has a plan?
- **Risk** (1-5): How risky is the change? (lower = better)

Then check for prioritization issues:
- **Misordered**: High-score issue has no label, low-score issue has `planned`
- **Blocked chains**: Issue A blocks Issue B, but B has higher priority labels
- **Label inconsistency**: Issue has `planned` but no implementation plan in comments
- **Orphaned follow-ups**: Follow-up issue whose parent was closed but follow-up has no plan

### Step 6: Generate Recommendations

For each finding, produce a specific actionable recommendation:

**For duplicates**:
```
DUPLICATE: #A and #B describe the same thing
  Action: Close #B as duplicate of #A (A is more detailed)
  Command: gh issue close B --reason "not planned" --comment "Duplicate of #A" -R {owner}/{repo}
```

**For overlaps**:
```
OVERLAP: #A and #B both touch [component] [feature]
  Action: Consolidate into #A, update #A body to include #B scope
  Command: [manual — requires body edit]
```

**For stale issues**:
```
STALE: #C references [deprecated component/file]
  Action: Close as not planned
  Command: gh issue close C --reason "not planned" --comment "References deprecated [component/file]" -R {owner}/{repo}
```

**For prioritization fixes**:
```
PRIORITY: #D (score 28) has no labels but should be prioritized above #E (score 15, has 'planned')
  Action: Add 'enhancement' label to #D
  Command: gh issue edit D --add-label "enhancement" -R {owner}/{repo}
```

### Step 7: Take Actions (unless --dry-run)

If `DRY_RUN=false`:

#### 7a. Close confirmed duplicates
For each duplicate pair with HIGH confidence:
```bash
gh issue close <LOWER_QUALITY_NUMBER> --reason "not planned" -R {owner}/{repo} --comment "$(cat <<'EOF'
Closing as duplicate of #<BETTER_NUMBER>.

**Reason**: <brief explanation of why these are duplicates>
EOF
)"
```

#### 7b. Close stale issues (only with --close-stale flag)
For each stale issue with HIGH confidence:
```bash
gh issue close <NUMBER> --reason "not planned" -R {owner}/{repo} --comment "$(cat <<'EOF'
Closing as stale.

**Reason**: <staleness reason>

If this is still relevant, please reopen with updated context.
EOF
)"
```

#### 7c. Fix labels
For issues with incorrect or missing labels:
```bash
gh issue edit <NUMBER> --add-label "<label>" -R {owner}/{repo}
gh issue edit <NUMBER> --remove-label "<label>" -R {owner}/{repo}
```

#### 7d. Link related issues
For overlapping issues that should reference each other, post a comment:
```bash
gh issue comment <NUMBER> --body "Related: #<OTHER_NUMBER> (overlapping scope — consider batching)" -R {owner}/{repo}
```

### Step 8: Report Results

Present a comprehensive report:

```markdown
# Issue Triage Report

**Generated**: [date]
**Open Issues Audited**: [count]
**Mode**: [full / dry-run]

## Summary

| Category | Count |
|----------|-------|
| Total open issues | N |
| Duplicates found | N |
| Stale issues | N |
| Overlapping (batchable) | N |
| Prioritization issues | N |
| Actions taken | N |

## Duplicates

| Issue A | Issue B | Confidence | Action |
|---------|---------|------------|--------|
| #NNN — Title | #NNN — Title | High | Closed #B as dup |

## Stale Issues

| Issue | Reason | Confidence | Action |
|-------|--------|------------|--------|
| #NNN — Title | References deleted file X | High | Closed / Flagged |

## Overlapping Issues (Batch Candidates)

| Cluster | Issues | Shared Scope | Recommendation |
|---------|--------|-------------|----------------|
| [Component] [feature] | #A, #B | Both add [feature] to [component] | Batch into single PR |

## Prioritization

### Current Priority Order (by score)

| Rank | Issue | Type | Impact | Urgency | Ready | Risk | Score | Labels |
|------|-------|------|--------|---------|-------|------|-------|--------|
| 1 | #NNN | ... | ... | ... | ... | ... | ... | ... |

### Prioritization Issues Found

| Issue | Problem | Recommendation |
|-------|---------|----------------|
| #NNN | Has `planned` but no plan in comments | Remove `planned` or run `/plan-issue` |

## Issue Backlog by Component

| Component | Open Issues | Planned | Needs Planning |
|-----------|-------------|---------|----------------|
| [Component A] | 3 | 1 | 2 |
| [Component B] | 2 | 0 | 2 |
| ... | ... | ... | ... |

## Recommended Next Actions

1. [Highest priority actionable recommendation]
2. [Second recommendation]
3. [Third recommendation]

## Actions Taken in This Run

| Action | Issue | Detail |
|--------|-------|--------|
| Closed as duplicate | #NNN | Duplicate of #NNN |
| Added label | #NNN | Added `enhancement` |
| Linked issues | #NNN, #NNN | Posted related-issue comments |
```

---

## Rules

1. **Be conservative with closures**. Only close duplicates with HIGH confidence. For MEDIUM confidence, recommend but don't act.
2. **Never close issues with `planned` label** without explicit user confirmation — these have approved implementation plans.
3. **Never modify issue body or comment content**. You may close issues, add/remove labels, and post new comments.
4. **Prefer consolidation over deletion**. When two issues overlap, recommend merging scope into the better-written one rather than closing both.
5. **Check the codebase** before declaring an issue stale. Verify files still exist, features haven't been implemented, etc.
6. **Flag but don't close** issues with the `follow-up` label unless their parent is still open AND the follow-up scope was absorbed back into the parent.
7. **Report everything** in structured tables so the user can quickly review and override decisions.
8. **Idempotent**: Running this command twice should not create duplicate comments or re-close already-closed issues.
9. **Do not create new issues.** This command audits and cleans up — it does not generate new work items.
10. **Use Task subagents** for parallel codebase verification when checking multiple issues for staleness simultaneously.

---

## Integration with Parallel Agents

For complex decision-making (e.g., determining if two issues truly duplicate), use parallel agents:

```bash
~/.claude/scripts/parallel_agent.sh --json --timeout 300 \
  "Are issues #A and #B duplicates? Issue A: [summary]. Issue B: [summary]."
```

Use parallel agent consensus to increase confidence in closure decisions:
- >= 80% consensus: HIGH confidence
- 50-79% consensus: MEDIUM confidence
- < 50% consensus: LOW confidence (recommend only, don't act)

---

## Example Usage

```bash
# Audit all open issues, report only
/issue-triage --dry-run

# Audit and fix, but don't close stale issues
/issue-triage

# Audit and close stale issues with high confidence
/issue-triage --close-stale

# Audit specific issues only
/issue-triage 123, 456, 789
```
