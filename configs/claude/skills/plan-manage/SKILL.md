---
name: plan-manage
description: |
  Manage plan lifecycle in .claude/.plans with create, review, execute, archive,
  and abandon flows, including optional parallel-agent orchestration.
---

# Plan Management

Manage implementation plans in `.claude/.plans/` with optional parallel agent orchestration
for cross-verified planning.

## Arguments

- `<action>` — One of: `list`, `create`, `review`, `execute`, `archive`, `abandon` (default: **list**)
- `<description>` — Task description (required for `create`)
- `<filename>` — Plan filename (required for `execute`, optional for `review`, `archive`, `abandon`)
- `<issue-number>` — GitHub/GitLab issue number (accepted by `create` and `execute`)

**Issue number detection**: If the argument matches `^#?\d+$` (e.g., `42` or `#42`), treat it as an issue number.

---

## Actions

Determine the requested action from the user's argument (default: **list**).

### list

1. Read all `*.md` files in `.claude/.plans/` (excluding TEMPLATE.md and README.md)
2. For each plan, extract: filename, status, title, created date, deliverables (checked/total)
3. Flag any plan not modified in 7+ days as **STALE**
4. Display a summary table

### create

Orchestrate a cross-verified implementation plan using parallel agents when appropriate.
Accepts a text description **or** an issue number (`42` / `#42`).

#### Step 0: Detect input type

1. If the argument matches `^#?\d+$`, treat it as an **issue number**:
   a. Fetch the issue via `~/.claude/scripts/git_ops.sh issue-view N`.
   b. Extract the issue title and body.
   c. **Posting disposition**: If the issue body is <200 characters or contains no markdown headings (`##`),
   the plan will replace the issue body later (Step 3a). Otherwise, the plan will be posted as a comment.
   d. Use the issue title + body as the task description for subsequent steps.
2. If the argument is plain text, use it directly as the description (existing behavior).

#### Step 1: Preflight — Determine if parallel agents are needed

Evaluate the task description against trigger criteria:

- **Security-sensitive**: auth, crypto, secrets, input validation
- **Architectural**: new services, API changes, schema modifications, new integrations
- **Large scope**: 3+ files expected to change
- **Critical logic**: payments, user data, compliance

If **any** criterion matches → use parallel agents (Step 2a).
Otherwise → single-agent planning (Step 2b).

#### Step 2a: Parallel Agent Planning

1. Run parallel agents with the task description:

   ```bash
   ~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 600 \
     --cursor-model flash --claude-model sonnet \
     "Propose an implementation plan for: <DESCRIPTION>.
      For each proposal, include:
      - Approach (1-2 sentences)
      - Ordered deliverables as a checklist
      - Files to create or modify
      - Risks and mitigations
      - Estimated scope (small/medium/large)"
   ```

2. Parse the JSON output. Extract each agent's proposed plan.

3. **If consensus >= 80%**: Merge into a unified plan directly.

4. **If consensus 50-79%**: Spawn a Task(general-purpose) synthesis agent:

   ```text
   Task(
     subagent_type: "general-purpose",
     prompt: "Using ~/.claude/prompts/synthesis.md, synthesize these planning proposals:
              Task: <DESCRIPTION>
              Cursor: <CURSOR_OUTPUT>
              Gemini: <GEMINI_OUTPUT>
              Claude: <CLAUDE_OUTPUT>
              Return: unified approach, merged deliverables, combined risks,
              and note where agents disagreed."
   )
   ```

5. **If consensus < 50%**: Present all three proposals to the user via
   AskUserQuestion and let them choose or combine.

#### Step 2b: Single-Agent Planning

1. Explore the codebase with Glob, Grep, Read to understand current structure
2. Draft the plan based on the task description and codebase context

#### Step 3: Save the Plan

1. Read `.claude/.plans/TEMPLATE.md`
2. Populate all sections from the synthesized/drafted plan:
   - **Objective**: From the task description
   - **Context**: Why this work is needed, any relevant codebase context discovered
   - **Deliverables**: Ordered checklist from the planning output
   - **Related Files**: Files to create or modify
   - **Risks**: From agent proposals (merged if parallel)
   - **Completion Criteria**: Derived from deliverables
   - **Log**: Record whether parallel agents were used and the consensus score
   - **Issue**: `#N` (if created from an issue, otherwise omit)
3. Save the plan file:
   - **Issue-linked**: `.claude/.plans/YYYYMMDD-issue-N-short-description.md`
   - **Text-only**: `.claude/.plans/YYYYMMDD-short-description.md`
4. Present the final plan to the user for approval

#### Step 3a: Post plan to issue (issue-linked only)

If the plan was created from an issue:

1. Apply the `planned` label — create it if it doesn't exist (see `.claude/config/labels.yml` for canonical definitions):

   ```bash
   ~/.claude/scripts/git_ops.sh label-create "planned" --color "1D76DB" --description "Implementation plan exists for this issue" --force 2>/dev/null || true
   ~/.claude/scripts/git_ops.sh issue-edit N --add-label "planned"
   ```

2. Post the plan to the issue based on the posting disposition from Step 0:
   - **Replace body**: Use `git_ops.sh issue-edit N --body <plan-markdown>`
   - **Add comment**: Use `git_ops.sh issue-comment N --body <plan-markdown>`

### review

1. If a filename is provided, review that single plan. Otherwise review all active plans.
2. For each plan, report:
   - Deliverable completion progress (checked vs total)
   - Days since last modification
   - Whether it should be archived (all done) or flagged as stale (7+ days)
3. **For stale plans (7+ days)**: Optionally re-evaluate with parallel agents:
   - Send the plan + current codebase state to agents
   - Ask: "Is this plan still valid? Should it be updated, completed, or abandoned?"
   - Present the recommendation to the user
4. Suggest actions for each plan

### execute

Implement all unchecked deliverables in an active plan, then archive it on completion.
Accepts a plan filename **or** an issue number (`42` / `#42`).

#### Step 0: Resolve plan source

1. If the argument matches `^#?\d+$`, treat it as an **issue number**:
   a. Search for a matching plan: `glob .claude/.plans/*issue-N*`.
   b. If found, use that plan file.
   c. If not found, check the issue body/comments for a plan (look for `## Deliverables` section).
   d. If still not found, abort with: `"No plan found for issue #N. Run: /plan-manage create N"`
2. If the argument is a filename, use it directly (existing behavior).
3. If no argument, ask which plan to execute.

#### Step 1: Setup issue tracking (issue-linked only)

If the plan has an `**Issue**: #N` field or was resolved from an issue number:

1. Apply the `in-progress` label, remove `planned` (see `.claude/config/labels.yml`):

   ```bash
   ~/.claude/scripts/git_ops.sh label-create "in-progress" --color "FBCA04" --description "Implementation is actively underway" --force 2>/dev/null || true
   ~/.claude/scripts/git_ops.sh issue-edit N --add-label "in-progress" --remove-label "planned"
   ```

2. Post an initial progress comment with a deliverable status table:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-comment N --body "## Execution Progress
   | # | Deliverable | Status |
   |---|-------------|--------|
   | 1 | First item  | ⏳ Pending |
   | 2 | Second item | ⏳ Pending |
   ..."
   ```

#### Step 2: Execute deliverables

1. Read the plan file. Verify `**Status**: ACTIVE`. If not active, abort with a message.
2. Parse the **Deliverables** section. Identify all unchecked items (`- [ ]`).
   - If no unchecked deliverables remain, skip to Step 4 (finalize).
3. For each unchecked deliverable, in order:
   a. Create a task (TaskCreate) for the deliverable with subject, description, and activeForm.
   b. Set task status to `in_progress` (TaskUpdate).
   c. Read the **Related Files** and **Implementation Notes** sections for context.
   d. Implement the deliverable:
   - Use Read, Glob, Grep to understand current code.
   - Use Edit or Write to make changes.
   - Use Bash for any shell operations (tests, builds, etc.).
     e. After implementation, check off the deliverable (`- [x]`) in the plan file (Edit).
     f. Set task status to `completed` (TaskUpdate).
     g. **Issue-linked only**: Update the progress comment via
     `~/.claude/scripts/git_ops.sh issue-comment-edit-last N --body "<updated-table>"`

**Error handling**: If a deliverable fails, keep its task as `in_progress`, log the failure
in the plan's **Log** section, and ask the user how to proceed (skip, retry, or abort).

#### Step 3: Post-execution review (issue-linked only)

If the plan is linked to an issue:

1. Run a cross-verified review of all changes:

   ```bash
   ~/.claude/scripts/parallel_agent.sh --json --validate --timeout 600 \
     --cursor-model flash --claude-model sonnet \
     "Review the implementation for issue #N. Changes: <SUMMARY_OF_CHANGES>"
   ```

2. Post the review results as a comment on the issue.
3. Based on the verdict:
   - **APPROVED**: Apply `done` label, remove `in-progress`, close the issue (see `.claude/config/labels.yml`):

     ```bash
     ~/.claude/scripts/git_ops.sh label-create "done" --color "0E8A16" --description "Implementation complete and validated" --force 2>/dev/null || true
     ~/.claude/scripts/git_ops.sh issue-edit N --add-label "done" --remove-label "in-progress"
     ~/.claude/scripts/git_ops.sh issue-close N
     ```

   - **NEEDS_REVIEW / BLOCKED**: Keep the issue open, post findings as a comment, ask the user how to proceed.

#### Step 4: Finalize

1. Update the plan's **Log** with an execution summary entry.
2. Update `**Status**: ACTIVE` to `**Status**: COMPLETED` in the plan file.
3. Move the plan to `.claude/.plans/.archive/`.
4. Report a summary of all changes made.

### archive

1. Accept a filename argument or ask which plan to archive
2. Verify all deliverables are checked off
3. Move the plan to `.claude/.plans/.archive/`

### abandon

1. Accept a filename argument or ask which plan to abandon
2. Confirm with the user
3. Move the plan to `.claude/.plans/.abandoned/`

---

## Parallel Agent Trigger Criteria

| Action    | Parallel Agents | Trigger                                          |
| --------- | --------------- | ------------------------------------------------ |
| `create`  | CONDITIONAL     | Security, architecture, 3+ files, critical logic |
| `execute` | CONDITIONAL     | Post-execution review for issue-linked plans     |
| `review`  | CONDITIONAL     | Stale plans (7+ days) being re-evaluated         |
| `list`    | NEVER           | Read-only metadata scan                          |
| `archive` | NEVER           | File move only                                   |
| `abandon` | NEVER           | File move only                                   |

**Model selection for planning** (balanced — not security-critical):

| Agent  | Model  | Reason                                     |
| ------ | ------ | ------------------------------------------ |
| Cursor | flash  | Good reasoning for architectural proposals |
| Claude | sonnet | Balanced planning capability               |
| Gemini | flash  | Broad knowledge for diverse approaches     |

---

## Tool Usage

- **Read**, **Glob**, **Grep**: Inspect plans, explore codebase during planning
- **Bash**: Run `parallel_agent.sh` (create/review/execute), `git_ops.sh` (issue operations), `mv` (archive/abandon), `date`
- **Write**: Save new plans from template
- **Edit**: Check off deliverables (`- [x]`) during execute
- **Task**: Spawn synthesis agent when agents disagree (consensus < 80%)
- **AskUserQuestion**: Present plan for approval, resolve low-consensus disagreements
