---
description: Plan lifecycle with parallel agent orchestration for create/review
allowed-tools: Read, Glob, Grep, Bash, Write, Task
argument-hint: [list|create|review|archive|abandon] [description-or-filename]
---

# Plan Management

Manage implementation plans in `.claude/.plans/` with optional parallel agent orchestration
for cross-verified planning.

## Arguments

- `<action>` — One of: `list`, `create`, `review`, `archive`, `abandon` (default: **list**)
- `<description>` — Task description (required for `create`)
- `<filename>` — Plan filename (optional for `review`, `archive`, `abandon`)

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
3. Save as `.claude/.plans/YYYYMMDD-short-description.md`
4. Present the final plan to the user for approval

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

| Action | Parallel Agents | Trigger |
|--------|----------------|---------|
| `create` | CONDITIONAL | Security, architecture, 3+ files, critical logic |
| `review` | CONDITIONAL | Stale plans (7+ days) being re-evaluated |
| `list` | NEVER | Read-only metadata scan |
| `archive` | NEVER | File move only |
| `abandon` | NEVER | File move only |

**Model selection for planning** (balanced — not security-critical):

| Agent | Model | Reason |
|-------|-------|--------|
| Cursor | flash | Good reasoning for architectural proposals |
| Claude | sonnet | Balanced planning capability |
| Gemini | flash | Broad knowledge for diverse approaches |

---

## Tool Usage

- **Read**, **Glob**, **Grep**: Inspect plans, explore codebase during planning
- **Bash**: Run `parallel_agent.sh` (create/review), `mv` (archive/abandon), `date`
- **Write**: Save new plans from template
- **Task**: Spawn synthesis agent when agents disagree (consensus < 80%)
- **AskUserQuestion**: Present plan for approval, resolve low-consensus disagreements
