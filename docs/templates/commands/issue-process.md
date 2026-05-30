# Role: Senior Technical Architect & Orchestrator

## Objective

Process the provided GitHub Issue into a fully implemented, tested, and validated feature. You act as the Orchestrator, coordinating domain-specific Sub-Agents for each component and using parallel agent tooling for planning and validation.

**Issue to process**: $ARGUMENTS

---

## Customization Required

Before using this command, customize the following sections for your project:

### Project Context (Required)

```markdown
**Architecture**: [Your architecture pattern]
**Languages**: [Languages used]
**Infrastructure**: [Key infrastructure]

### Component/Service Map

| Component | Language | Responsibility |
|-----------|----------|----------------|
| [Name] | [Lang] | [Brief description] |
```

### Key Constraints (Required)

```markdown
- [Constraint 1]
- [Constraint 2]
```

### Test Commands (Required)

Define the test commands for your project:

```bash
# Unit tests
make test
# OR
npm test
# OR
pytest

# Integration tests
make test-integration
# OR
npm run test:integration

# Lint
make lint
# OR
npm run lint
```

### Agent Files (Optional)

If your project has per-component agent files:

```markdown
| Component | Agent File | Scope |
|-----------|-----------|-------|
| [Name] | `[path]/AGENTS.md` | [What it covers] |
```

---

## Workflow (STRICT)

### Step 0: Context Compaction

Before doing anything else, run `/compact` to summarize and free up context space. This ensures maximum available context for the multi-step implementation workflow that follows. Do not skip this step.

### Step 0.5: Plan Gate — Validate plan-issue Has Run

Before planning or implementing anything, verify that the issue has been through the planning phase (`/plan-issue` or `/issue-plan`):

1. Fetch the issue metadata:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-view $ARGUMENTS --json labels,body,comments -R {owner}/{repo}
   ```

   **Replace `{owner}/{repo}` with your repository.**

2. **Check for `planned` label**:
   - If the issue **has** the `planned` label → proceed to step 3
   - If the issue **does not** have the `planned` label → **HARD STOP**. Report to the user:
     > This issue has not been planned yet. Run `/plan-issue $ARGUMENTS` first to generate an implementation plan, then re-run `/process-issue $ARGUMENTS`.

     Do not proceed. Do not implement anything. Stop here.

3. **Extract the latest implementation plan**:
   - Search the issue **comments** (newest first) for the most recent comment containing `## Implementation Plan` or `## Updated Implementation Plan`. If found, use that comment as the plan source.
   - If no matching comment is found, check the **issue body** for `## Implementation Plan` or `# Implementation Plan`.
   - If neither contains a recognizable plan, **HARD STOP** and report:
     > The `planned` label is present but no implementation plan was found in the issue body or comments. Run `/plan-issue $ARGUMENTS` to generate one.

4. **Parse the plan** and extract the following sections (not all may be present — extract what exists):
   - **Summary** — high-level scope and approach
   - **Affected Components** — which components to delegate to and their impact levels
   - **File Changes** (new files and modified files) — the implementation blueprint
   - **Database Migrations** — migration files to create
   - **Schema Changes** — schema updates
   - **Implementation Order** — the dependency-ordered sequence of tasks
   - **Testing Checklist** — specific tests to write
   - **Cross-Component Checklist** — multi-component coordination items

   This parsed plan becomes the **primary implementation blueprint** for Steps 1-4. Do not re-derive the plan from scratch — implement what was planned.

---

### Step 1: Ingestion & Checklist Extraction

1. Read the provided GitHub Issue from $ARGUMENTS (use `~/.claude/scripts/git_ops.sh issue-view` if a number/URL is given). You already have the issue data from Step 0.5 — reuse it rather than re-fetching.
2. **Extract checklists from body AND comments**: Parse the issue body **and** every comment for GitHub-flavored markdown checklists (`- [ ]` / `- [x]` items). Track these as **acceptance criteria** throughout the workflow. For each checklist item, record:
   - The item text
   - Whether it's in the issue **body** or a **comment** (and if a comment, its `comment_id` — available from the API response)
   - Its current checked/unchecked state
   Each checklist item becomes a trackable deliverable that must be addressed during implementation. If neither the body nor comments contain checklists, note this and proceed — the implementation summary will still be posted.
3. **Cross-reference checklists with the plan**: Map each checklist item to the relevant task(s) in the implementation plan extracted in Step 0.5. This ensures no acceptance criteria are missed during implementation.
4. **Validate the plan against current codebase state**: Run a quick sanity check — do the files referenced in the plan still exist? Have they changed significantly since the plan was created? If the plan references files that no longer exist or have been substantially modified, warn the user that the plan may be stale and suggest re-running `/plan-issue`.
5. Use the **Implementation Order** from the plan to produce the per-component task breakdown. Only run a cross-component impact analysis if the plan lacks an Implementation Order section:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --timeout 600 \
     --analyze "Analyze impact of: [ISSUE_SUMMARY]. Components: [AFFECTED_COMPONENTS]"
   ```

### Step 2: Implementation (Sub-Agent Delegation)

Follow the **Implementation Order** from the plan extracted in Step 0.5. For each affected component, in the order specified by the plan:

1. Read the component's agent file (if it exists): `[path]/AGENTS.md`
2. Reference the relevant language standards (if they exist): `docs/standards/[lang]/STANDARDS.md`
3. Delegate to a Task sub-agent with:
   - The **specific file changes** from the plan's "File Changes" section for this component (new files to create, existing files to modify, and what to change in each)
   - The **database migrations** from the plan (if applicable to this component)
   - The **schema changes** from the plan (if applicable)
   - Component-specific context from its `AGENTS.md`
   - Requirement to write implementation code AND unit tests from the plan's "Testing Checklist"
4. If schema changes are needed (as specified in the plan's "Schema Changes" section):
   - Update schema definition files
   - Run code generation commands if applicable
   - Update all affected components (producer/server first, then consumers/clients)
5. Review the sub-agent's output against the plan. Reject deviations from the planned approach. If a sub-agent identifies a problem with the plan (e.g., the planned approach won't work due to a constraint not caught during planning), document the deviation and rationale — do not silently diverge.

### Step 3: Verification

Once all sub-agents have completed their tasks:

1. **Unit tests**: Run your project's unit test command
2. **Integration tests**: Run your project's integration test command (if applicable)
3. **Lint**: Run your project's linter

**On failure**: Recall the specific component sub-agent responsible for the failing code to fix the error. Do not fix it yourself without the sub-agent's context.

### Step 4: Final Validation

Once all tests pass:

1. Run parallel agent validation on each modified file:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --validate --timeout 600 \
     --review /absolute/path/to/modified_file
   ```

2. Evaluate consensus:
   - **>= 80%**: High confidence — proceed to Step 5 with status `processed`
   - **50-79%**: Medium confidence — proceed to Step 5 with status `needs-review`, include disagreements
   - **< 50%**: Low confidence — proceed to Step 5 with status `needs-review`, escalate to user

### Step 5: Issue Update & Closure

Once validation is complete, update checkboxes, post an implementation update on the GitHub issue, and label it.

#### 5a. Update checkboxes in issue body and comments

For each checklist item extracted in Step 1, update its checkbox to reflect the implementation outcome:

- **Completed items**: Change `- [ ]` to `- [x]`
- **Partially completed or blocked items**: Leave as `- [ ]` (explain in the implementation comment)

**To update the issue body**:

```bash
# Fetch current body, update checkboxes, then PATCH
BODY=$(gh api repos/{owner}/{repo}/issues/{number} --jq '.body')
# Modify BODY string to check off completed items (replace "- [ ] <item>" with "- [x] <item>")
gh api repos/{owner}/{repo}/issues/{number} -X PATCH --field body="$UPDATED_BODY"
```

**To update a comment**:

```bash
# Fetch current comment body, update checkboxes, then PATCH
COMMENT_BODY=$(gh api repos/{owner}/{repo}/issues/comments/{comment_id} --jq '.body')
# Modify COMMENT_BODY string to check off completed items
gh api repos/{owner}/{repo}/issues/comments/{comment_id} -X PATCH --field body="$UPDATED_COMMENT_BODY"
```

**Important**:

- Only modify checkbox lines (`- [ ]` → `- [x]`). Do not alter any other content in the body or comment.
- Use the comment IDs recorded in Step 1 to target the correct comments.
- If a checklist item was only partially completed, leave it unchecked and document the gap in the implementation comment (Step 5c).

#### 5b. Determine final status

Based on Step 4 consensus and test results:

| Condition | Label | Meaning |
|-----------|-------|---------|
| All tests pass AND consensus >= 80% | `processed` | Fully implemented, validated, ready to merge |
| Tests pass but consensus 50-79%, OR minor items unresolved | `needs-review` | Implemented but requires human review |
| Any test failure, consensus < 50%, or blocked items | `needs-review` | Partial implementation, issues documented |

#### 5c. Build the checklist status report

If the issue body or comments contained checklists (extracted in Step 1), produce a checklist status table mapping each original item to its implementation outcome. Include the **source** column to indicate whether the item came from the issue body or a comment:

```markdown
### Checklist Status

| # | Source | Item | Status | Notes |
|---|--------|------|--------|-------|
| 1 | Body | [original checklist item text] | ✅ Done / ⚠️ Partial / ❌ Blocked | [brief explanation or commit ref] |
| 2 | Comment #123 | [original checklist item text] | ✅ Done / ⚠️ Partial / ❌ Blocked | [brief explanation] |
```

- **✅ Done**: Fully implemented and tested
- **⚠️ Partial**: Partially implemented, explain what remains
- **❌ Blocked**: Could not be completed, explain why

If neither the issue body nor any comments had checklists, skip this table.

#### 5d. Post implementation comment

Post a structured comment on the issue using `~/.claude/scripts/git_ops.sh issue-comment`:

```bash
~/.claude/scripts/git_ops.sh issue-comment <ISSUE_NUMBER> --body "$(cat <<'EOF'
## Implementation Update

**Status**: `processed` | `needs-review`
**Consensus Score**: [X]%
**Branch**: `<branch-name>` (if applicable)

### Summary

[2-4 sentence summary of what was implemented, which components were modified, and key decisions made]

### Changes

| Component | Files Modified | Description |
|---------|---------------|-------------|
| [component] | [file list] | [what changed] |

### Checklist Status

[Include the checklist status table from 5c, or "No checklists in original issue or comments." if none]

### Test Results

- **Unit tests**: ✅ Pass / ❌ Fail
- **Integration tests**: ✅ Pass / ❌ Fail / ⏭️ Skipped
- **Lint**: ✅ Pass / ❌ Fail

### Validation

- **Parallel agent consensus**: [X]% ([High/Medium/Low] confidence)
- **Disagreements**: [list any, or "None"]

### Follow-up Items

[List any remaining work, known limitations, or items flagged for human review. "None" if fully complete.]
EOF
)" -R {owner}/{repo}
```

#### 5e. Parse follow-up items from implementation comment

After posting the implementation comment in 5d, extract actionable follow-up items from **four sources**. For each item, record: `title` (short derived name), `origin` (which source), `body_text` (original item text), and `context` (1-2 sentences of surrounding context).

**Source 1 — Follow-up Items section**: Parse the `### Follow-up Items` section of the comment posted in 5d. Each bullet point is a follow-up item, unless the section contains only "None".

**Source 2 — Checklist Status (Partial)**: Parse the `### Checklist Status` table from 5c. Any row with status `⚠️ Partial` becomes a follow-up item. Use the `Item` column as `body_text` and the `Notes` column as `context`.

**Source 3 — Checklist Status (Blocked)**: Same as Source 2 but for rows with status `❌ Blocked`.

**Source 4 — Future Enhancements from Plan**: If the implementation plan extracted in Step 0.5 contains a section titled `## Future Enhancements (Not in Scope)` or `## Future Enhancements`, parse each bullet point as a follow-up item. Set origin to `"Future Enhancements"`.

If zero actionable items are found across all four sources, skip step 5f entirely.

#### 5f. Create follow-up issues

For each follow-up item parsed in 5e, create a new GitHub issue.

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
   **Created by**: `process-issue` command

   ### Description

   <ORIGINAL_ITEM_TEXT>

   ### Context

   <1-2 sentences on what was implemented, why this remains, any constraints.>
   EOF
   )"
   ```

   - Replace all `<PLACEHOLDERS>` with actual values from the parent issue and the parsed item.
   - Add relevant component labels when the follow-up clearly applies to a specific component.
   - Add type labels (e.g., `bug`, `enhancement`, `test`) when clearly applicable.

3. **Post a summary comment on the parent issue** listing all created follow-up issues:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-comment <PARENT_NUMBER> --body "$(cat <<'EOF'
   ### Follow-up Issues Created

   | # | Title | Origin |
   |---|-------|--------|
   | #<NEW_ISSUE_NUMBER> | <TITLE> | <ORIGIN_SECTION> |

   These issues were automatically created from follow-up items identified during processing of this issue.
   EOF
   )" -R {owner}/{repo}
   ```

#### 5g. Apply label

```bash
# Add the status label
~/.claude/scripts/git_ops.sh issue-edit <ISSUE_NUMBER> --add-label "done" -R {owner}/{repo}
# OR
~/.claude/scripts/git_ops.sh issue-edit <ISSUE_NUMBER> --add-label "needs-review" -R {owner}/{repo}
```

If the label does not yet exist in the repository, create it first:

```bash
# Create labels if they don't exist (idempotent — gh will error silently if label exists)
# Labels defined in .claude/config/labels.yml — use 'done' instead of deprecated 'processed'
~/.claude/scripts/git_ops.sh label-create "done" --description "Implementation complete and validated" --color "0E8A16" -R {owner}/{repo} 2>/dev/null || true
~/.claude/scripts/git_ops.sh label-create "needs-review" --description "Requires human review before completion" --color "E3A21A" -R {owner}/{repo} 2>/dev/null || true
```

#### 5h. Commit changes (if status is "processed")

If the final status is `processed` (Step 5b), commit all changes with the issue reference:

1. **Check for uncommitted changes**:

   ```bash
   git status --porcelain
   ```

   - If empty, skip to 5i (nothing to commit)
   - If changes exist, proceed to commit

2. **Generate commit message**:
   - Analyze staged/unstaged changes with `git diff --stat`
   - Review implementation summary from 5d
   - Generate a concise commit message following conventional commits format:

     ```
     <type>(<scope>): <description>

     <body explaining the changes in 2-4 sentences>

     Fixes #<ISSUE_NUMBER>
     ```

   - Types: feat, fix, refactor, test, docs, chore
   - Scope: affected component(s) or area
   - Always include `Fixes #<ISSUE_NUMBER>` at the end

3. **Stage and commit**:

   ```bash
   git add -A
   git commit --no-verify -m "$(cat <<'EOF'
   <generated commit message>
   EOF
   )"
   ```

   - Use `--no-verify` to skip pre-commit hooks (already validated in Step 3)
   - Log the commit hash for the user notification in 5i

4. **Handle commit failures**:
   - If commit fails, note the error and proceed to 5i (user will manually commit)
   - Do not block issue closure on commit failure

**Important**: Only commit if status is `processed`. If status is `needs-review`, skip this step entirely and let the user review before committing.

#### 5i. Notify user

Report the final status to the user in the chat, including:

- The label applied (`processed` or `needs-review`)
- A link to the posted comment
- **Commit status** (if step 5h executed):
  - If committed: commit hash and short summary
  - If skipped (needs-review): note that user must commit manually
  - If failed: error message and recommendation to commit manually
- Any items requiring human attention
- Follow-up issues created (count, issue numbers, and titles), or "No follow-up issues" if none were created

---

## Critical Rules

1. **Respect all architectural constraints** defined in your project context.
2. **Follow the implementation plan** from Step 0.5. Do not deviate without documenting why.
3. **Never skip tests.** All code must be tested before validation.
4. **Be specific in follow-up issues.** Include enough context that someone else can pick them up.
5. **Only commit when status is "processed".** Let humans review "needs-review" implementations.

---

## Example Usage

```bash
# Process a specific issue
/process-issue 123

# Process from issue URL
/process-issue https://github.com/owner/repo/issues/456
```
