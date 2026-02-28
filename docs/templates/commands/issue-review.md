# Role: Issue Audit Agent

## Objective

Review all open GitHub issues labeled `processed`, verify their checklists are complete, and take action: **close** issues that are fully complete, or **add `needs-review` label** to issues with unchecked items.

**Arguments (optional)**: $ARGUMENTS

If arguments are provided, they may specify a single issue number to audit. Otherwise, audit all open issues with the `processed` label.

---

## Customization Required

### Repository (Required)

Replace `{owner}/{repo}` with your repository path in all Git CLI commands below (works with GitHub and GitLab).

---

## Workflow

### Step 1: Fetch Issues

Fetch all open issues with the `processed` label (or the specific issue if provided):

```bash
# All processed issues
~/.claude/scripts/git_ops.sh issue-list --label processed --state open --json number,title,labels --limit 100 -R {owner}/{repo}

# Single issue (if $ARGUMENTS is a number)
~/.claude/scripts/git_ops.sh issue-view $ARGUMENTS --json number,title,labels,body,comments -R {owner}/{repo}
```

If no issues are found, report "No open issues with the `processed` label" and stop.

### Step 2: Audit Each Issue

For each issue, fetch full details (body + comments):

```bash
~/.claude/scripts/git_ops.sh issue-view <NUMBER> --json number,title,body,comments,labels -R {owner}/{repo}
```

#### 2a. Extract Checklists

Parse the issue **body** and every **comment** for GitHub-flavored markdown checklists:

- `- [ ]` = unchecked item
- `- [x]` = checked item

Record:

- Total checklist items found
- Checked count
- Unchecked count
- Source (body or comment ID)
- The text of each unchecked item

#### 2b. Determine Verdict

| Condition                                 | Verdict          | Action                                           |
| ----------------------------------------- | ---------------- | ------------------------------------------------ |
| All checklist items are checked (`- [x]`) | **CLOSE**        | Close the issue                                  |
| No checklists found in body or comments   | **CLOSE**        | Close the issue (no acceptance criteria to fail) |
| Any unchecked items remain (`- [ ]`)      | **NEEDS-REVIEW** | Add `needs-review` label                         |

#### 2c. Detect follow-up items and check for existing follow-ups

**2c-i. Parse candidate follow-up items** from all Implementation Update comments on the issue. For each comment containing `## Implementation Update`, extract items from:

- `### Follow-up Items` section — each bullet point (skip "None")
- `### Checklist Status` table — rows with `⚠️ Partial` status
- `### Checklist Status` table — rows with `❌ Blocked` status
- `## Future Enhancements (Not in Scope)` or `## Future Enhancements` from the implementation plan (found in a plan comment containing `## Implementation Plan`)

For each candidate, record: `title`, `origin`, `body_text`, `context`.

**2c-ii. Check for existing follow-up issues** by searching the issue comments for a comment containing `### Follow-up Issues Created`. If found:

- Extract issue numbers from the table rows (pattern: `#<NUMBER>`)
- Verify each extracted issue still exists: `~/.claude/scripts/git_ops.sh issue-view <NUMBER> --json number,title,state -R {owner}/{repo}`
- Match each verified issue against the parsed candidates by title similarity

**2c-iii. Classify each candidate** as:

- `already-created` — a matching follow-up issue was found in 2c-ii
- `needs-creation` — no matching follow-up issue exists

### Step 3: Take Action

#### For CLOSE verdicts

```bash
~/.claude/scripts/git_ops.sh issue-close <NUMBER> -R {owner}/{repo}
```

#### For NEEDS-REVIEW verdicts

```bash
~/.claude/scripts/git_ops.sh label-create "needs-review" --description "Requires human review before completion" --color "E3A21A" -R {owner}/{repo} 2>/dev/null || true
~/.claude/scripts/git_ops.sh issue-edit <NUMBER> --add-label "needs-review" -R {owner}/{repo}
```

#### For issues with uncreated follow-ups (from 2c)

If any candidates were classified as `needs-creation` in step 2c-iii, create follow-up issues:

1. **Ensure the `follow-up` label exists**:

   ```bash
   ~/.claude/scripts/git_ops.sh label-create "follow-up" --description "Spawned from another issue during implementation" --color "D4C5F9" -R {owner}/{repo} 2>/dev/null || true
   ```

2. **Create each follow-up issue** using the standardized template:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-create --title "Follow-up: <DERIVED_TITLE>" --label "follow-up" -R {owner}/{repo} --body "$(cat <<'EOF'
   <!-- follow-up-from: #<PARENT_NUMBER> -->
   ## Follow-up from #<PARENT_NUMBER>

   **Parent Issue**: #<PARENT_NUMBER> — <PARENT_TITLE>
   **Origin Section**: <"Follow-up Items" | "Checklist Status (Partial)" | "Checklist Status (Blocked)" | "Future Enhancements">
   **Created by**: `issue-review` command

   ### Description

   <ORIGINAL_ITEM_TEXT>

   ### Context

   <1-2 sentences on what was implemented, why this remains, any constraints.>
   EOF
   )"
   ```

   - Replace all `<PLACEHOLDERS>` with actual values.
   - Add relevant component and type labels when clearly applicable.

3. **Post a summary comment on the parent issue**:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-comment <PARENT_NUMBER> --body "$(cat <<'EOF'
   ### Follow-up Issues Created (Audit)

   | # | Title | Origin |
   |---|-------|--------|
   | #<NEW_ISSUE_NUMBER> | <TITLE> | <ORIGIN_SECTION> |

   These issues were automatically created during audit review of this issue.
   EOF
   )" -R {owner}/{repo}
   ```

Only process `needs-creation` items — items classified as `already-created` are skipped to maintain idempotency.

### Step 4: Report Results

Present a summary table to the user:

```markdown
## Processed Issues Audit

| #   | Title     | Checklist    | Follow-ups         | Verdict      | Action Taken         |
| --- | --------- | ------------ | ------------------ | ------------ | -------------------- |
| 123 | Feature X | 5/5 checked  | 0 exist, 0 created | CLOSE        | Closed               |
| 124 | Feature Y | 3/7 checked  | 2 exist, 1 created | NEEDS-REVIEW | Labeled needs-review |
| 125 | Bug fix Z | No checklist | 0 exist, 0 created | CLOSE        | Closed               |

### Issues Needing Attention

**#124 — Feature Y** (4 unchecked items):

- [ ] Item A (body)
- [ ] Item B (comment #456)
- [ ] Item C (comment #456)
- [ ] Item D (comment #789)

### Follow-up Issues

**From #124 — Feature Y**:

- Already existed: #130 — Follow-up: Add validation for edge case, #131 — Follow-up: Update docs
- Created in this audit: #140 — Follow-up: Handle blocked integration test
```

List the unchecked items for each NEEDS-REVIEW issue so the user can quickly see what remains. Include the follow-up issues section showing both pre-existing and newly created follow-ups grouped by parent issue.

---

## Rules

1. **Do not modify issue content** (body or comments). You may close issues, add labels, create new follow-up issues, and post new comments.
2. **Only audit open issues**. Closed issues are skipped.
3. **Be conservative**: If there is any ambiguity about whether a checklist item is satisfied, mark it as NEEDS-REVIEW rather than CLOSE.
4. **Process all issues in a single run** for efficiency. Use parallel agents or batch API calls where possible.
5. **Report results in a table** so the user can quickly see the outcome.
6. **Maintain idempotency**: Don't create duplicate follow-up issues if they already exist.

---

## Example Usage

```bash
# Audit all open processed issues
/issue-review

# Audit a specific issue
/issue-review 123
```
