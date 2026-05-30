# Role: Technical Planning Architect

## Objective

Analyze the provided GitHub Issue, explore the codebase, develop a detailed implementation plan, validate it with parallel agents, and post the plan directly to the GitHub issue. **You must NEVER implement anything** — no file writes, no code changes, no branches, no commits. Planning and posting only.

**Issue to plan**: $ARGUMENTS

---

## Customization Required

Before using this command, customize the following sections for your project:

### Project Context (Required)

Replace the placeholders with your project's architecture:

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

Document your project's architectural constraints that implementations must respect:

```markdown
### Key Constraints

- [Constraint 1, e.g., "No direct database access across service boundaries"]
- [Constraint 2, e.g., "All API changes must be backwards-compatible"]
- [Constraint 3, e.g., "Authentication required for all endpoints"]
```

**Examples of constraints**:

- Communication patterns (REST only, gRPC required, event-driven, etc.)
- Data access rules (schema boundaries, ORM requirements)
- Deployment order requirements (migrations before code, feature flags)
- Security requirements (authentication, authorization, encryption)

### Agent Files (Optional)

If your project has per-component agent files (AGENTS.md), list them:

```markdown
| Component | Agent File | Scope |
|-----------|-----------|-------|
| [Name] | `[path]/AGENTS.md` | [What it covers] |
```

### Standards Files (Optional)

If your project has coding standards documents:

```markdown
| Language | Standards File |
|----------|---------------|
| [Lang] | `docs/standards/[lang]/STANDARDS.md` |
```

---

## Workflow (STRICT)

### Step 0: Context Compaction

Before doing anything else, run `/compact` to summarize and free up context space. This ensures maximum available context for the multi-step planning workflow that follows. Do not skip this step.

### Step 0.5: HARD STOP — Planning Only

**YOU MUST NOT:**

- Write, create, modify, or delete any file in the repository
- Run builds, linters, formatters, or test commands
- Create branches or commits
- Run `make` targets or build scripts
- Generate code from schemas

**YOU MAY ONLY:**

- Read files (Read, Glob, Grep tools)
- Run Git CLI commands to read/write issues (GitHub/GitLab)
- Run `~/.claude/scripts/parallel_agent.py` for validation
- Spawn read-only Task sub-agents (Explore type only)

If you catch yourself about to write code or modify a file, STOP immediately. Your only deliverable is a plan posted to the GitHub issue.

---

### Step 1: Fetch & Parse the Issue

1. Fetch the issue:

   ```bash
   ~/.claude/scripts/git_ops.sh issue-view $ARGUMENTS --json title,body,labels,state,comments -R {owner}/{repo}
   ```

   **Replace `{owner}/{repo}` with your repository.**

2. If the issue is not found, warn the user and stop. If the issue is closed, warn but proceed with planning.

3. **Determine posting disposition** — decide whether to REPLACE the issue body or ADD a comment:

   **REPLACE the body** if ANY of these are true:
   - Body is empty or whitespace-only
   - Body is shorter than 200 characters
   - Body contains no markdown headings (no lines starting with `##`)

   **ADD a comment** if ALL of these are true:
   - Body is 200+ characters
   - Body contains at least one markdown heading (`##`)

   Record this decision — you will use it in Step 6.

4. Summarize the issue requirements in 2-3 sentences. If the body is empty or minimal, derive scope from the title.

---

### Step 2: Identify Affected Components

1. Map the issue requirements against your Component Map.
2. Classify the issue type to guide component identification:

   | Issue Type | Typically Affects |
   |-----------|-------------------|
   | Frontend-only (UI, UX, styling) | Web/Mobile components |
   | New data field end-to-end | Data layer, API, Frontend |
   | New external integration | Integration layer, Data layer |
   | Algorithm/logic change | Core logic components |
   | API schema change | API, Clients/Consumers |
   | New event type | Publisher, all consumers |
   | Infrastructure/config | Infrastructure files, potentially all components |

   **Customize this table for your architecture.**

3. Produce an impact table:

   | Component | Affected? | Why | Impact Level |
   |-----------|-----------|-----|-------------|
   | (each component) | Yes/No | Brief reason | High/Medium/Low/None |

---

### Step 3: Explore the Codebase (Read-Only)

Use Task sub-agents with `subagent_type: Explore` to gather implementation context. **Never use sub-agents that write files.**

For **each affected component**:

1. Read its agent file (if it exists) for architecture and patterns
2. Explore the component's directory structure
3. Find similar existing patterns that the implementation should follow
4. Note key files that will need modification

For **cross-component changes**, also explore:

- Infrastructure files (databases, message queues, etc.)
- Shared libraries or utilities
- Configuration files
- API contracts or schema definitions

Record all findings — they form the basis of your plan.

---

### Step 4: Design the Implementation Plan

Structure the plan using this template. Include only sections that are relevant to the issue.

```markdown
# Implementation Plan: [Issue Title]

> **Issue**: #[number] — [title]
> **Generated by**: Claude (plan-issue command)
> **Consensus Score**: [score]% ([High/Medium/Low] confidence)
> **Disposition**: [Body replacement / Comment addition]

## Summary

[2-3 sentence summary of what this issue requires and the chosen approach]

## Research & Validation

[Key findings from codebase exploration — existing patterns found, architectural constraints identified]

## Current State → Proposed State

| Aspect | Current | Proposed |
|--------|---------|----------|
| ... | ... | ... |

## Design Rationale

[Why this approach was chosen over alternatives. Reference architectural constraints.]

## Agent Disagreements & Resolutions

(Include only if parallel agent consensus < 100%)

| Topic | Agent A | Agent B | Resolution |
|-------|---------|---------|------------|
| ... | ... | ... | ... |

## Affected Components

| Component | Impact Level | Changes Required |
|-----------|-------------|-----------------|
| ... | ... | ... |

## File Changes

### New Files
- `path/to/new/file.ext` — [Purpose]
  - [Key implementation detail]
  - [Key implementation detail]

### Modified Files
- `path/to/existing/file.ext` — [What changes]
  - [Specific change 1]
  - [Specific change 2]

## Database Migrations

(Include only if schema changes are needed)

- Migration: `[path]/[YYYYMMDD]_description.[ext]`
  - [What the migration does]
  - [Backwards compatibility note]

## Schema Changes

(Include only if API/data schema changes are needed)

- File: `[path/to/schema/file]`
  - [New/modified fields]
  - [Backwards compatibility: versioning, deprecated fields]

## Cross-Component Checklist

(Include only for multi-component changes)

- [ ] Schema updated → code generation → all consumers updated
- [ ] Publisher deployed before consumer for new events
- [ ] Database migration is backwards-compatible
- [ ] API changes are backwards-compatible or versioned
- [ ] [Custom constraint from your project]

## Accessibility Requirements

(Include only for frontend changes)

- [ ] [Specific a11y requirement]

## Security Considerations

(Include for changes affecting auth, data access, external APIs)

- [ ] [Specific security consideration]

## Testing Checklist

- [ ] [Specific test to write, with file path]
- [ ] [Integration test scenario]

## Implementation Order

1. [First task — e.g., "Database migration"]
2. [Second task — e.g., "Update API handler"]
3. [Continue in dependency order...]

## Future Enhancements (Not in Scope)

- [Thing that could be done later but is not part of this issue]
```

---

### Step 5: Validate with Parallel Agents

1. Run parallel agent validation:

   ```bash
   ~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 600 \
     "Review this implementation plan for issue #[NUMBER]: [PLAN_SUMMARY].
      Evaluate: completeness, component coverage, architectural correctness, implementability,
      missing edge cases, and whether the implementation order respects dependencies."
   ```

2. If `parallel_agent.py` is not available or fails, note that validation was skipped and proceed.

3. Evaluate consensus:
   - **>= 80%**: High confidence — proceed with the plan as-is
   - **50-79%**: Medium confidence — include agent disagreements in the plan, note areas needing human review
   - **< 50%**: Low confidence — add a warning banner at the top of the plan: `> ⚠️ LOW CONFIDENCE: Parallel agent consensus was below 50%. This plan requires careful human review.`

4. Incorporate useful agent feedback into the plan before posting.

---

### Step 6: Post to GitHub Issue

Based on the disposition determined in Step 1:

**If REPLACING the body:**

```bash
~/.claude/scripts/git_ops.sh issue-edit $ARGUMENTS --body-file - -R {owner}/{repo} <<'PLAN_EOF'
[FULL PLAN MARKDOWN]
PLAN_EOF
```

**If ADDING a comment:**

```bash
~/.claude/scripts/git_ops.sh issue-comment $ARGUMENTS --body-file - -R {owner}/{repo} <<'PLAN_EOF'
## Updated Implementation Plan

[FULL PLAN MARKDOWN]
PLAN_EOF
```

After posting, confirm success by re-fetching the issue:

```bash
~/.claude/scripts/git_ops.sh issue-view $ARGUMENTS --json title,body,comments -R {owner}/{repo}
```

Verify the plan appears in the body or as the latest comment.

#### 6b. Apply label

Add the `planned` label to the issue to indicate that an implementation plan has been posted:

```bash
# Create label if it doesn't exist (idempotent — gh will error silently if label exists)
~/.claude/scripts/git_ops.sh label-create "planned" --description "Implementation plan posted to issue" --color "1D76DB" -R {owner}/{repo} 2>/dev/null || true

# Add the label
~/.claude/scripts/git_ops.sh issue-edit $ARGUMENTS --add-label "planned" -R {owner}/{repo}
```

---

### Step 7: STOP

Report to the user:

- Issue URL
- Label applied (`planned`)
- Affected components
- Parallel agent consensus score (or "skipped" if unavailable)
- Disposition used (body replacement vs. comment)
- Areas flagged for human review (if any)

**Do not implement. Do not ask if the user wants you to implement. Your work is done.**

---

## Critical Rules

1. **NEVER write, create, modify, or delete any files in the repository.** This command is planning-only. No code, no branches, no commits. Your only output is a plan posted to the GitHub issue.
2. **Respect all architectural constraints** defined in your project context.
3. **The plan must be actionable** — detailed enough that someone unfamiliar with the codebase could implement it by following the file changes and implementation order.
4. **Always post the plan to the GitHub issue.** Never just print the plan to the terminal. The issue is the deliverable.
5. **Be specific about file paths.** Use actual paths from the codebase, not placeholders.
6. **Include backwards compatibility notes** for any schema, API, or database changes.
7. **Consider dependencies** in the implementation order — don't suggest changes that would break until their dependencies are in place.

---

## Example Usage

```bash
# Plan a specific issue
/issue-plan 123

# Plan from issue URL
/issue-plan https://github.com/owner/repo/issues/456
```
