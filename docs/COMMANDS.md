# Commands Guide

> Building custom commands for Claude Code with Manifest

**Last Updated**: 2026-06-15
**Audience**: Command developers, advanced users
**Prerequisites**: Manifest installed, basic understanding of Markdown and Bash

---

## Table of Contents

1. [Built-in Commands](#built-in-commands)
2. [Command Reference (generated)](#command-reference) — full catalog, every command
3. [What Are Commands](#what-are-commands)
4. [Command Structure](#command-structure)
5. [Command Patterns](#command-patterns)
6. [Building State Machine Commands](#building-state-machine-commands)
7. [Parallel Agent Integration](#parallel-agent-integration)
8. [Error Handling](#error-handling)
9. [Testing Commands](#testing-commands)
10. [Examples](#examples)

---

## Built-in Commands

Manifest ships with 80+ skills and 1 CLI tool; the table below is a curated
subset of the most-used commands. The **full, always-current catalog** is in the
generated [Command Reference](#command-reference) below (every command, grouped
by category) — or run `/help [query]` in-session for searchable discovery. Both
are built from each skill's `SKILL.md` frontmatter, the authoritative source.

| Command | Description | Parallel Agents |
|---------|-------------|-----------------|
| `/git-commit` | Full commit pipeline: docs, pull, pre-commits, commit, push | CONDITIONAL (Phase 3) |
| `/docs-improve-readme` | Improve README documentation | NO |
| `/docs-generate-diagrams` | Generate Mermaid architecture diagrams | CONDITIONAL (5+ modules) |
| `/docs-improve` | Diataxis documentation framework analysis | CONDITIONAL (>500 lines) |
| `/docs-all` | Run docs-improve-readme/docs-generate-diagrams/docs-improve as sub-agents in one pass | CONDITIONAL |
| `/graphify` | Map a codebase/docs into a queryable knowledge graph (graphify CLI) | NO |
| `/python-refactor` | Python codebase security and quality analysis | ALWAYS |
| `/shell-refactor` | Bash/Shell script security and quality analysis | ALWAYS |
| `/node-refactor` | Node.js/TypeScript codebase security and quality analysis | ALWAYS |
| `/go-refactor` | Go codebase security and quality analysis | ALWAYS |
| `/terraform-refactor` | Terraform/OpenTofu IaC security, modularity, and quality analysis | ALWAYS |
| `/issue-triage` | Linear issue audit: duplicates, staleness, priority validation | CONDITIONAL |
| `/issue-prioritize` | Score and rank open issues by impact/urgency/readiness/risk | CONDITIONAL |
| `/issue-dev-auto` | Autonomously develop one opted-in (`auto-dev`-labeled) issue end-to-end — selects next ready issue, implements test-first, verifies, opens a PR. **Now also monitors automation PRs and (opt-in via `PR_MERGE_LOOP_APPLY=1`) merges them to main once the gated decision clears — CI green, comments addressed, #360 gate Tier-1 pass, consensus ≥0.80; fail-closed to a human otherwise.** Self-paced, stops after 5 empty runs | NO |
| `pr_merge_loop.sh run [--apply]` | Bounded self-paced merge-loop pass: enforces a hard 10-minute ceiling, stops after 5 consecutive empty runs, serializes merges via `loop_lock` (one in flight), exits 11 on halt (post-merge `main` red). Default dry-run; pass `--apply` or set `PR_MERGE_LOOP_APPLY=1` for real merges. `/loop /issue-dev-auto` is the outer re-invoker. Standalone `run` orchestrates monitoring/merge only — it does not itself push code revisions; a PR needing `revise` requires the SKILL (`/loop /issue-dev-auto`) to apply fixes, otherwise it polls until the ceiling. | NO |
| `/issue-sync-pr` | Hook-triggered: on PR open, back-link + advance linked issue to `needs-review` + ensure closing keyword (fail-open) | NO |
| `/issue-sync-commit` | Hook-triggered: on branch commit, advance a `planned` issue to `in-progress`, deduped (fail-open) | NO |
| `/plan-manage` | Plan lifecycle with parallel agent orchestration | CONDITIONAL |
| `/smoke-manage` | Catalog-driven smoke tests; UI steps run via browser-use `mode: agent` | NO |
| `/session-checkpoint` | Create compact checkpoint summary when context is high | NO |
| `/env-check` | Verify CLI tools, auth, config syntax, MCP, symlinks | NO |
| `/config-audit` | Detect cross-platform config drift and broken symlinks | NO |
| `/version-pin` | Enforce specific, hashed version pins in dependency files (auto-fix on demand; warn-only save hook) | ALWAYS (Tier 1) |
| `/pr-review` | Review all open PRs and recommend a disposition per PR (analysis-only) | NO |
| `/pr-monitor` | Babysit a just-opened PR/MR: watch CI to green (fix failures), address Copilot findings, tag Jules and handle its feedback. Auto-triggers on `gh pr create`/`glab mr create` | NO |
| `/branch-clean` | Prune merged/gone/stale branches safely (dry-run by default, local-only) | CONDITIONAL (--apply) |
| `/repo-clean` | Review-then-confirm cleanup sweep of open PRs and stale/merged/gone branches (GitHub/GitLab/local) | CONDITIONAL (close/prune path) |
| `/skill-evolve` | Promote SkillClaw-evolved skills into a review PR (dry-run by default); requires SkillClaw enabled | NO |
| `/pass-cli` | Retrieve credentials from Proton Pass vaults via `pass-cli` agent CLI | NO |
| `/spec-review` | Independent Antigravity (agy) cross-reference of spec/plan/tasks for internal consistency; on-demand or via fail-open PostToolUse save hook (content-hash debounced, detached); analysis-only; works with speckit and superpowers layouts; silent-mode findings land in `.spec-review/feedback.md`. `--mode product\|technical` distinguishes the two lifecycle spec-review passes | NO |
| `/lifecycle-run` | Drive a unit of work through the codified nine-phase state-gated lifecycle (Specify→…→Verify) with hard gating; entry is a ticket URL/issue key (GitHub/GitLab/Linear/Jira); the smoke-test suite is the Verify gate. Backed by `lifecycle.sh` (constitution Principle VI) | NO |
| `/a11y-audit` | WCAG 2.2 AA accessibility audit | NO |
| `/antipattern-detect` | Detect recurring antipatterns from lint, test, and review feedback | NO |
| `/ci-setup` | Configure CI/CD pipelines for a target repository (GitHub Actions or GitLab CI) | NO |
| `/code-audit` | Auto-triggered security and quality checks | AUTO (always when triggered) |
| `/metrics-report` | Visualize agent efficiency metrics | NO |
| `/learning-capture` | Capture structured lessons learned | NO |
| `/performance-check` | Frontend performance audit: bundle size, Core Web Vitals, caching | NO |
| `/project-scaffold` | Initialize new projects with quality gates and Manifest integration | NO |
| `/ux-review` | UX audit: accessibility, responsive design, performance budgets | NO |
| `/project-verify` | Run linters, tests, and security scans in parallel | CONDITIONAL |
| `/token-benchmark` | Measure Manifest context token overhead and quality delta across providers; regenerates `docs/TOKEN_BENCHMARK.md` | NO |

**CLI tool** (installed to `~/.local/bin/`):

| Tool | Description |
|------|-------------|
| `sync-skills` | Sync `.skillshare/skills/` to all home targets; uses `MANIFEST_ROOT` env var |

The `code-audit` skill auto-triggers on security-sensitive code, large files (>500 lines),
or complex files (>10 functions or >5 classes).

---

## Label Management

Issue labels are defined in a central registry at `configs/claude/config/labels.yml` and synced
across GitHub, GitLab, and Linear.

### Canonical Labels

| Label | Color | Hex | Description |
|-------|-------|-----|-------------|
| `planned` | Blue | `#1D76DB` | Implementation plan exists for this issue |
| `in-progress` | Yellow | `#FBCA04` | Implementation is actively underway |
| `needs-review` | Orange | `#E3A21A` | Requires human review before completion |
| `done` | Green | `#0E8A16` | Implementation complete and validated |
| `follow-up` | Lavender | `#D4C5F9` | Spawned from another issue during implementation |
| `future` | Green | `#C2E0C6` | Queued for future prioritization and scheduling |
| `auto-dev` | Purple | `#5319E7` | Eligible for the autonomous issue developer (/issue-dev-auto) |
| `needs-human` | Dark red | `#B60205` | Auto-dev could not complete; needs a human |
| `blocked-dependency` | Gray | `#6A737D` | Has an unmet dependency; excluded from the auto-dev queue |
| `ready-to-merge` | Green | `#0E8A16` | Auto-dev verified the PR but lacked merge authority; awaiting a human merge |
| `loop-active` | Yellow | `#FBCA04` | Transient lock — the auto-dev merge loop is acting on this PR |
| `hold` | Red-orange | `#D93F0B` | Do not auto-merge; the loop must route this PR to a human |

**Deprecated**: `processed` — use `done` instead (same color and purpose).

### Syncing Labels

```bash
# Dry-run — see what would be created
~/.claude/scripts/label_sync.sh --dry-run

# Sync all labels to the current Git platform (GitHub or GitLab)
~/.claude/scripts/label_sync.sh

# Sync only to Linear
~/.claude/scripts/label_sync.sh --platform linear --team ENG

# Validate without creating
~/.claude/scripts/label_sync.sh --validate

# Via git_ops.sh wrapper
~/.claude/scripts/git_ops.sh label-sync
~/.claude/scripts/git_ops.sh label-sync --dry-run
```

### Managing Labels

```bash
# List labels on current platform
~/.claude/scripts/git_ops.sh label-list

# Create a single label on current platform
~/.claude/scripts/git_ops.sh label-create "my-label" --color "FF0000" --description "My label"

# Create a label in Linear
~/.claude/scripts/linear_ops.sh label-create --name "my-label" --color "FF0000" --team ENG

# List labels in Linear
~/.claude/scripts/linear_ops.sh label-list --team ENG
```

---

## Issue-Linking Hooks

Two opt-in, fail-open hooks keep the linked GitHub/GitLab issue in sync with
development activity (skills `issue-sync-pr` and `issue-sync-commit`, over the shared
`issue_support.sh` engine). They never block a git action.

```bash
# Enable (unified PostToolUse hook); add --native for a guarded git post-commit hook
configs/claude/scripts/install_issue_hooks.sh --enable [--native]

# Preview / debug without mutating the tracker
configs/claude/scripts/issue_support.sh sync-pr --dry-run
configs/claude/scripts/issue_support.sh resolve --branch 005-my-feature --json

# Disable (keeps the skills; flips the runtime gate off and removes the hooks)
configs/claude/scripts/install_issue_hooks.sh --remove
```

Behavior: PR opened → linked issue advances to `needs-review` + back-link + `Closes #N`;
commit on a branch → a `planned` issue advances to `in-progress` (deduped). Coverage
boundary: PR creation via the web UI or raw `gh`/`glab` outside a tool is not
auto-observed — run `issue_support.sh sync-pr` manually there. Config:
`command_config.yml → tool_policies.{pr,commit}-issue-sync`.

---

## What Are Commands

Commands are markdown files that define reusable workflows for Claude Code. They enable:

- **Complex multi-step operations** (deployments, migrations)
- **Automated workflows** (GitHub issue management)
- **Architecture analysis** (event tracing, API mapping)
- **Project management** (commit pipelines, PR creation)

**Location**: `configs/claude/skills/` (each skill is a directory with a `SKILL.md` file)

**Invocation**: Users run skills with `/skill-name` in Claude Code.

---

## Command Structure

### Basic Command Format

```markdown
---
description: Brief description of what the command does
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, Task, AskUserQuestion
argument-hint: [argument-name (optional)]
---

# Command Name

Full description of the command's purpose and use cases.

## Arguments

- `$ARGUMENTS` - Description of expected arguments
- If not provided: default behavior

## Instructions

Step-by-step instructions for Claude to execute...

## Examples

Usage examples...
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | Short description (appears in command list) |
| `allowed-tools` | Yes | Comma-separated list of tools Claude can use |
| `argument-hint` | No | Hint about expected arguments |

### Allowed Tools

| Tool | Purpose |
|------|---------|
| `Bash` | Run shell commands (git, docker, npm, etc.) |
| `Read` | Read file contents |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents |
| `Edit` | Modify files |
| `Write` | Create new files |
| `Task` | Spawn sub-agents |
| `AskUserQuestion` | Ask user for input during execution |
| `Skill` | Invoke other skills/commands |

---

## Command Patterns

### Pattern 1: Analysis Commands

**Purpose**: Analyze code, generate reports, trace architecture

**Structure**:

```markdown
1. Scan codebase (Glob, Grep)
2. Analyze patterns
3. Generate report
4. Output results
```

**Examples**:

- `/docs-generate-diagrams` - Generate Mermaid diagrams
- `/trace-events` - Map event publishers/consumers
- `/trace-api` - Map API calls

**Tool Usage**: Read-only (Read, Glob, Grep)

---

### Pattern 2: Automation Commands

**Purpose**: Automate repetitive workflows

**Structure**:

```markdown
1. Validate preconditions
2. Execute workflow steps
3. Handle errors
4. Report status
```

**Examples**:

- `/git-commit` - Full commit pipeline (regenerate docs, pull, pre-commits, commit, push)
- `/issue-process` - Process GitHub issue
- `/full-deployment-pipeline` - Deploy with validation

**Tool Usage**: Read + Write (Bash, Edit, Write, Skill for invoking other commands)

**Example Structure** (`/git-commit`):

1. Phase 1: Documentation Generation (`/docs-generate-diagrams`, `/docs-improve`, `/docs-improve-readme`)
2. Phase 2: Pull Latest & Resolve Conflicts (git fetch, pull --rebase)
3. Phase 3: Pre-commit Checks (pre-commit run --all-files with auto-fixes)
4. Phase 4: Stage & Commit (auto-detect issue references, append "Fixes #N")
5. Phase 5: Push (git push with fallback handling)

---

### Pattern 3: Interactive Commands

**Purpose**: Require user input during execution

**Structure**:

```markdown
1. Gather context
2. Ask user for decision (AskUserQuestion)
3. Execute based on choice
4. Confirm results
```

**Examples**:

- `/issue-prioritize` - Score issues (user input on criteria)
- `/issue-plan` - Design implementation (user chooses approach)

**Tool Usage**: Read + AskUserQuestion

---

### Pattern 4: Orchestration Commands

**Purpose**: Coordinate multiple sub-agents or services

**Structure**:

```markdown
1. Analyze cross-service impact
2. Delegate to sub-agents (Task)
3. Collect results
4. Synthesize recommendations
```

**Examples**:

- `/issue-process` - Delegates to service-specific sub-agents
- Headless orchestration prompts

**Tool Usage**: Task, Read, Grep

---

## Building State Machine Commands

**Pattern Documentation**: See [Command State Machine Pattern](templates/patterns/command-state-machine.md)

State machine commands structure complex operations as sequential phases with
validation gates, error recovery, and progress tracking.

### When to Use State Machines

✅ **Use for**:

- Multi-step processes with dependencies (deployments, migrations)
- Operations requiring rollback (destructive changes)
- Long-running tasks needing progress tracking

❌ **Don't use for**:

- Simple single-step commands
- Read-only analysis
- Quick queries

### State Machine Structure

````markdown
## Command Phases

Execute these phases **in order**. Each phase must succeed before proceeding to the next.

### Phase 1: [Name]

**Success Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

**On Failure**:
- Retry up to N times
- If still failing: [action]

**Implementation**:
```bash
# Command to run
```

### Phase 2: [Next Phase]

[...]

````

### Key Components

1. **Phase Definition**
   - Clear name and purpose
   - Explicit success criteria
   - Defined failure handling

2. **Error Recovery**
   - Automatic retry with backoff
   - Selective retry by error type
   - User confirmation on failure
   - Automatic rollback

3. **Progress Tracking**
   - Summary table at end
   - Phase status (pass/fail/warn/skip/retry)
   - Duration per phase
   - Overall outcome

4. **Validation Gates**
   - Each phase validates before proceeding
   - Dependencies enforced
   - Rollback points defined

### Example State Machine

**Full Deployment Pipeline**: `templates/commands/full-deployment-pipeline.md`

5-phase deployment:

```text

Phase 1: Run Tests
    ↓
Phase 2: Build Artifacts
    ↓
Phase 3: Validate Plan (parallel agents)
    ↓
Phase 4: Deploy (with automatic rollback)
    ↓
Phase 5: Verify Deployment

```

Each phase:

- Has retry logic (2x)
- Reports status
- Can rollback on failure

**Output Format**:

```text

## Deployment Pipeline Summary

| Phase | Status | Duration | Notes |
|-------|--------|----------|-------|
| 1. Run Tests | ✅ pass | 2m 15s | Coverage: 87% |
| 2. Build Artifacts | ✅ pass | 3m 42s | Image: myapp:abc123 |
| 3. Validate Plan | ✅ pass | 1m 8s | Consensus: 92% |
| 4. Deploy | ✅ pass | 45s | Rollout complete |
| 5. Verify | ⚠️ warn | 32s | 1 endpoint slow |

Overall: SUCCESS (with warnings)

```

### Common State Machine Patterns

1. **RVEV** (Read-Validate-Execute-Verify)
   - Read configuration
   - Validate configuration
   - Execute operation
   - Verify results

2. **PPPC** (Prepare-Process-Publish-Cleanup)
   - Prepare environment
   - Process data
   - Publish results
   - Cleanup temporary files

3. **FBTD** (Fetch-Build-Test-Deploy)
   - Fetch latest code
   - Build artifacts
   - Run tests
   - Deploy to environment

4. **BMVC** (Backup-Migrate-Validate-Commit)
   - Backup current state
   - Run migration
   - Validate new state
   - Commit changes (or rollback)

---

## Parallel Agent Integration

Commands can use parallel agents for cross-verification and consensus scoring.

### When to Use Parallel Agents

**ALWAYS use** for:

- Security-sensitive operations (deployments, migrations)
- Architectural decisions (schema changes, API changes)
- Code with high impact (>200 lines changed)

**CONDITIONALLY use** for:

- Moderate complexity changes
- When confidence is low

**SKIP** for:

- Read-only analysis
- Simple queries
- Documentation generation

### Integration Pattern

````markdown
## Parallel Agent Integration

This command [ALWAYS|CONDITIONALLY|NEVER] uses parallel agents.

When triggered, execute:
```bash
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 600 \
  --cursor-model [mini|flash|advanced] --claude-model [haiku|sonnet|opus] \
  [--analyze|--review] "[prompt or file path]"
```

Consensus scoring:

- >=80%: Auto-proceed with unified recommendation
- 50-79%: Highlight disagreements to user
- <50%: Block and escalate for human review

````

### Model Selection

| Task Criticality | Cursor Model | Claude Model | Gemini Model |
|-----------------|--------------|--------------|--------------|
| Critical (security, production) | `advanced` | `opus` | `pro` |
| Standard (code review, analysis) | `flash` | `sonnet` | `flash` |
| Light (suggestions, quick checks) | `mini` | `haiku` | `flash` |

### Parsing Results

```bash
# Run parallel agents
result=$(~/.claude/scripts/parallel_agent.py --json --validate --review "$file")

# Extract consensus score
consensus=$(echo "$result" | jq -r '.cross_verification.consensus_score')

# Extract agent outputs
gemini_output=$(echo "$result" | jq -r '.agents.gemini.output')
claude_output=$(echo "$result" | jq -r '.agents.claude.output')

# Decision based on consensus
if [[ $consensus -ge 80 ]]; then
  echo "✅ High confidence (${consensus}%)"
  proceed
elif [[ $consensus -ge 50 ]]; then
  echo "⚠️ Medium confidence (${consensus}%)"
  ask_user_whether_to_proceed
else
  echo "❌ Low confidence (${consensus}%)"
  block_and_report
fi
```

---

## Error Handling

### Basic Error Handling

```bash
# Check command success
if ! command_here; then
  echo "❌ Command failed"
  exit 1
fi

# Multiple conditions
if [[ ! -f "$file" ]]; then
  echo "❌ File not found: $file"
  exit 1
fi

if [[ ! -s "$file" ]]; then
  echo "❌ File is empty: $file"
  exit 1
fi
```

### Retry Logic

```bash
# Simple retry
for attempt in {1..3}; do
  if command_here; then
    break
  elif [[ $attempt -lt 3 ]]; then
    echo "Attempt $attempt failed, retrying..."
    sleep 5
  else
    echo "❌ Failed after 3 attempts"
    exit 1
  fi
done
```

### Rollback on Failure

```bash
# Save state before destructive operation
cp "$file" "$file.backup"

# Attempt operation
if ! dangerous_operation "$file"; then
  echo "Operation failed, rolling back..."
  mv "$file.backup" "$file"
  exit 1
fi

# Cleanup backup
rm "$file.backup"
```

### User Confirmation

````markdown
Use AskUserQuestion tool to ask user for input:

```json
{
  "questions": [{
    "question": "Operation failed. What would you like to do?",
    "header": "Error",
    "multiSelect": false,
    "options": [
      {
        "label": "Retry",
        "description": "Attempt the operation again"
      },
      {
        "label": "Skip",
        "description": "Skip this step and continue"
      },
      {
        "label": "Abort",
        "description": "Stop the command execution"
      }
    ]
  }]
}
```

````

---

## Testing Commands

### Manual Testing

```bash
# Test with real project
cd /path/to/test-project
claude run /your-command [arguments]

# Check exit code
echo $?  # Should be 0 for success
```

### Testing Error Handling

```bash
# Force failure at specific phase
export FORCE_PHASE_2_FAILURE=true
claude run /your-command

# Verify rollback works
# Verify error messages are clear
# Verify state is not corrupted
```

### Testing with Different Inputs

```bash
# Valid input
claude run /your-command valid-arg

# Invalid input
claude run /your-command invalid-arg

# No input
claude run /your-command

# Edge cases
claude run /your-command ""
claude run /your-command "very-long-argument-here..."
```

---

## Examples

### Example 1: Simple Analysis Command

**File**: `configs/claude/commands/count-todos.md`

````markdown
---
description: Count TODO comments in codebase
allowed-tools: Glob, Grep, Bash
---

# Count TODO Comments

Count and categorize TODO comments in the codebase.

## Instructions

1. Find all source files
2. Search for TODO comments
3. Categorize by priority
4. Generate report

```bash
# Find all TODO comments
todos=$(grep -rn "TODO\|FIXME\|HACK" --include="*.py" --include="*.js" --include="*.go" .)

# Count by type
todo_count=$(echo "$todos" | grep -c "TODO" || echo "0")
fixme_count=$(echo "$todos" | grep -c "FIXME" || echo "0")
hack_count=$(echo "$todos" | grep -c "HACK" || echo "0")

# Report
echo "## TODO Report"
echo ""
echo "| Type | Count |"
echo "|------|-------|"
echo "| TODO | $todo_count |"
echo "| FIXME | $fixme_count |"
echo "| HACK | $hack_count |"
echo ""
echo "**Total**: $((todo_count + fixme_count + hack_count))"
```

````

---

### Example 2: Interactive Command

**File**: `configs/claude/commands/create-feature-branch.md`

````markdown
---
description: Create feature branch with naming convention
allowed-tools: Bash, AskUserQuestion
argument-hint: [feature-description]
---

# Create Feature Branch

Create a feature branch following team naming conventions.

## Arguments

- `$ARGUMENTS` - Feature description (e.g., "add user authentication")

## Instructions

1. Validate current branch is main/master
2. Ensure working tree is clean
3. Ask user for feature type
4. Create branch with naming convention

**Current branch check**:
```bash
current_branch=$(git branch --show-current)
if [[ "$current_branch" != "main" && "$current_branch" != "master" ]]; then
  echo "❌ Must be on main/master branch"
  exit 1
fi

# Check working tree
if [[ -n $(git status --porcelain) ]]; then
  echo "❌ Working tree has uncommitted changes"
  exit 1
fi
```

**Ask user for feature type** (use AskUserQuestion tool):

- Options: "feature", "bugfix", "hotfix", "refactor"

**Create branch**:

```bash
feature_type="$USER_CHOICE"  # from AskUserQuestion
feature_desc="$ARGUMENTS"

# Convert to kebab-case
branch_name="${feature_type}/$(echo "$feature_desc" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"

git checkout -b "$branch_name"
echo "✅ Created branch: $branch_name"
```

````

---

### Example 3: State Machine Command

See: `templates/commands/full-deployment-pipeline.md`

Complete 5-phase deployment with:

- Sequential phases
- Retry logic
- Automatic rollback
- Parallel agent validation
- Summary table

---

## Best Practices

### 1. Clear Documentation

- **Description**: Short, action-oriented
- **Instructions**: Step-by-step, no ambiguity
- **Examples**: Show common use cases

### 2. Error Messages

- **Actionable**: Tell user how to fix
- **Specific**: What went wrong
- **Formatted**: Use ❌ ✅ ⚠️ for visibility

### 3. Tool Selection

- **Bash**: Use for git, docker, npm, system commands
- **Read/Glob/Grep**: Use for file operations
- **Edit/Write**: Minimize use, prefer Bash tools when possible
- **Task**: Use for sub-agent delegation

### 4. Validation

- **Input validation**: Check arguments early
- **Precondition checks**: Verify state before executing
- **Post-condition checks**: Verify operation succeeded

### 5. Progress Feedback

- **Start of phase**: "Starting Phase 2: Build Artifacts..."
- **During phase**: Show command output
- **End of phase**: "✅ Phase 2 complete (3m 42s)"
- **Final summary**: Table of all phases

---

## Related Documentation

- [Command State Machine Pattern](templates/patterns/command-state-machine.md) - Detailed pattern guide
- [Full Deployment Pipeline](templates/commands/full-deployment-pipeline.md) - Complete example
- [GitHub Workflow Commands](templates/commands/github-workflow/) - Issue management commands
- [Configuration Guide](./CONFIGURATION.md) - Parallel agent settings
- [Troubleshooting](./TROUBLESHOOTING.md) - Common command issues
- [SkillClaw](./SKILLCLAW.md) - Session capture, skill evolution, and `/skill-evolve` usage

---

## Contributing Commands

To contribute a command to Manifest:

1. Create command in `templates/commands/`
2. Follow structure guidelines above
3. Test with multiple projects
4. Add to `templates/README.md`
5. Submit PR to GitHub

**Command checklist**:

- [ ] Clear description
- [ ] Frontmatter complete
- [ ] Instructions step-by-step
- [ ] Error handling included
- [ ] Examples provided
- [ ] Tested on real project

---

## FAQ

**Q: How do I invoke a command?**
A: Type `/command-name` in Claude Code (without the .md extension)

**Q: Can commands call other commands?**
A: Yes, use the `Skill` tool to invoke other commands

**Q: How do I pass arguments?**
A: Arguments are passed as `$ARGUMENTS` to the command

**Q: Can commands modify files?**
A: Yes, if `Edit` or `Write` are in `allowed-tools`

**Q: How do I test commands?**
A: Create a test project and run `claude run /command-name`

**Q: Can commands use external APIs?**
A: Yes, via Bash (curl) if allowed in permissions

**Q: How do I debug failed commands?**
A: Check Claude Code logs, verify tool permissions, test bash commands manually

---

## Appendix: Complete Command Template

````markdown
---
description: [Short description of command]
allowed-tools: [Comma-separated list of tools]
argument-hint: [argument-name (optional)]
---

# [Command Name]

[Detailed description of what the command does and when to use it]

## Parallel Agent Integration (if applicable)

This command [ALWAYS|CONDITIONALLY|NEVER] uses parallel agents.

[Integration details if applicable]

## Arguments

- `$ARGUMENTS` - [Description]
- If not provided: [Default behavior]

---

## Instructions

[Step-by-step instructions for Claude to execute]

### Step 1: [First Step]

[Description]

```bash
[Command]
```

### Step 2: [Second Step]

[Description]

```bash
[Command]
```

---

## Error Recovery

**On Failure**:

- [Action 1]
- [Action 2]

---

## Examples

### Example 1: [Use Case]

```bash
/command-name argument
```

Expected output:

```text
[Output]
```

---

## Customization

[How to adapt for different projects]

---

## Related

- [Related command 1]
- [Related command 2]

````

## Command Reference

<!-- BEGIN GENERATED COMMANDS (command_catalog.py) — do not edit by hand -->
<!-- Regenerate: configs/claude/scripts/generate_commands_doc.py -->

_106 commands, generated from `.skillshare/skills/*/SKILL.md`._

### Git & PRs

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/branch-clean` | Identify and safely prune stale git branches — merged into the default branch, tracking a deleted remote ([gone]), or stale beyond a threshold. Dry-run and local-only by default (remote deletion opt-in); never touches protected or checked-out branches. | Identify and safely prune stale git branches — merged into the default branch, tracking a deleted remote ([gone]), or stale beyond a threshold. | available |
| `/git-commit` | Run the full Manifest commit pipeline — refresh docs, sync with remote, run pre-commit checks, then stage, commit, and push with safe failure handling. Use when committing and pushing through the whole pipeline, not a bare git commit. | Use when committing and pushing through the whole pipeline, not a bare git commit. | available |
| `/git-find-artifact` | Use when a referenced file (spec, plan, doc, config) does not exist at the given path on the current branch — search worktrees, all branches, and git history before assuming it is missing or asking the user. | Use when a referenced file (spec, plan, doc, config) does not exist at the given path on the current branch — search worktrees, all branches, and git history before assuming it is missing or asking the user. | available |
| `/issue-dev-auto` | Autonomously develop one opted-in ('auto-dev'-labeled) issue end-to-end: implement test-first and open a PR; an opt-in gated loop may also merge cleared PRs (dry-run by default). Dependency-blocked issues are skipped. Run unattended via /loop /issue-dev-auto. | Autonomously develop one opted-in ('auto-dev'-labeled) issue end-to-end: implement test-first and open a PR; an opt-in gated loop may also merge cleared PRs (dry-run by default). | available |
| `/issue-sync-commit` | Keep the linked GitHub/GitLab issue in sync when commits land on a feature branch: advance a planned issue to in-progress, deduplicated across commits. Runs as a hook (PostToolUse or native post-commit); fail-open (never blocks the commit). | Keep the linked GitHub/GitLab issue in sync when commits land on a feature branch: advance a planned issue to in-progress, deduplicated across commits. | available |
| `/issue-sync-pr` | Keep the linked GitHub/GitLab issue in sync when a pull/merge request is opened: back-link comment, advance status label to needs-review, ensure the closing keyword. Runs as a PostToolUse hook; fail-open (never blocks PR creation). | Keep the linked GitHub/GitLab issue in sync when a pull/merge request is opened: back-link comment, advance status label to needs-review, ensure the closing keyword. | available |
| `/pr-address-comments` | Use when your open PR receives review feedback (inline comments, Copilot/CodeRabbit, review-body, issue discussion) — resolve every item truthfully: fix real issues, decline wrong ones with evidence, never mark resolved without a verified fix. Distinct from analysis-only pr-review. | Use when your open PR receives review feedback (inline comments, Copilot/CodeRabbit, review-body, issue discussion) — resolve every item truthfully: fix real issues, decline wrong ones with evidence, never mark resolved without a verified fix. | available |
| `/pr-clean-base` | Use when a feature branch is rooted on another unmerged branch (or far behind main) and a rebase would replay unrelated commits or hit conflicts — isolate only your new commits onto a fresh branch off the real base. | Use when a feature branch is rooted on another unmerged branch (or far behind main) and a rebase would replay unrelated commits or hit conflicts — isolate only your new commits onto a fresh branch off the real base. | available |
| `/pr-merge-stacked` | Use when merging stacked PRs via gh/glab — `gh pr merge --delete-branch` on a parent CLOSES the dependent child instead of retargeting it; merge keeping the branch, retarget the child, then delete. | Use when merging stacked PRs via gh/glab — `gh pr merge --delete-branch` on a parent CLOSES the dependent child instead of retargeting it; merge keeping the branch, retarget the child, then delete. | available |
| `/pr-monitor` | Babysit a just-opened pull/merge request: watch CI to green, address GitHub Copilot findings, and tag Google Jules (@google-labs-jules) then handle its feedback. Use when a PR/MR is just opened: "babysit my PR", "get the bots to review it", "tag jules". | Use when a PR/MR is just opened: "babysit my PR", "get the bots to review it", "tag jules". | available |
| `/pr-reset-reapply` | When a feature branch's history is tangled with already-merged commits, reset to the default branch and reapply only the net diff as one clean PR | When a feature branch's history is tangled with already-merged commits, reset to the default branch and reapply only the net diff as one clean PR | available |
| `/pr-review` | Review all open pull/merge requests on the active platform (GitHub/GitLab), assess each for mergeability, checks, staleness, and whether still needed, and recommend a disposition (keep, merge, close, needs-rebase) per PR. Analysis-only — no mutations. | Review all open pull/merge requests on the active platform (GitHub/GitLab), assess each for mergeability, checks, staleness, and whether still needed, and recommend a disposition (keep, merge, close, needs-rebase) per PR. | available |
| `/pr-triage-bots` | Triage a queue of machine-generated PRs (Jules, Palette, Bolt, Copilot) — detect byte-identical duplicates, close redundant no-ops, merge verified micro-opts, and hold PRs that contradict repo conventions. | Triage a queue of machine-generated PRs (Jules, Palette, Bolt, Copilot) — detect byte-identical duplicates, close redundant no-ops, merge verified micro-opts, and hold PRs that contradict repo conventions. | available |
| `/repo-clean` | PR/MR + branch cleanup sweep: review every open PR and stale/merged/gone branch, then after you confirm close the dead PRs and prune branches (GitHub/GitLab/local). For any "tidy up my repo" ask spanning both; pick over pr-review or branch-clean. | PR/MR + branch cleanup sweep: review every open PR and stale/merged/gone branch, then after you confirm close the dead PRs and prune branches (GitHub/GitLab/local). | available |

### Documentation

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/docs-all` | Run docs-improve-readme, docs-generate-diagrams, and docs-improve in one command, dispatching each as a sub-agent and returning a consolidated report. Use to refresh the whole doc set at once. | Run docs-improve-readme, docs-generate-diagrams, and docs-improve in one command, dispatching each as a sub-agent and returning a consolidated report. | available |
| `/docs-generate-diagrams` | Generate and maintain Mermaid architecture diagrams that reflect current system structure, workflows, and integrations. | Generate and maintain Mermaid architecture diagrams that reflect current system structure, workflows, and integrations. | available |
| `/docs-improve` | Audit and improve project documentation using Diataxis and documentation quality best practices across the docs set. | Audit and improve project documentation using Diataxis and documentation quality best practices across the docs set. | available |
| `/docs-improve-readme` | Analyze and improve repository README documentation using code-derived facts, clear structure, and practical onboarding guidance. | Analyze and improve repository README documentation using code-derived facts, clear structure, and practical onboarding guidance. | available |

### Security

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/ci-audit-triggers` | Audit a GitHub Actions/GitLab CI workflow for attacker-influenceable triggers (pull_request_target, issue_comment, workflow_run) — pwn-request issues: fork head-ref checkout, ${{ }} injection, author_association gaps. Analysis-only; harden via ci-harden-workflow. | Audit a GitHub Actions/GitLab CI workflow for attacker-influenceable triggers (pull_request_target, issue_comment, workflow_run) — pwn-request issues: fork head-ref checkout, ${{ }} injection, author_association gaps. | available |
| `/ci-harden-workflow` | Build or harden a CI workflow running privileged actions (deploys, bot/agent invocation, secret use) on comment/PR triggers — identity gates, CODEOWNERS, branch protection, environments. Counterpart to ci-audit-triggers, which audits. | Build or harden a CI workflow running privileged actions (deploys, bot/agent invocation, secret use) on comment/PR triggers — identity gates, CODEOWNERS, branch protection, environments. | available |
| `/docker-audit-firewall` | Use when reviewing/writing host firewall rules (iptables/nftables) for a Docker-published port, or when a compose change adds a `ports:` mapping that replaces app-layer auth (Traefik, reverse-proxy) with a network ACL. | Use when reviewing/writing host firewall rules (iptables/nftables) for a Docker-published port, or when a compose change adds a `ports:` mapping that replaces app-layer auth (Traefik, reverse-proxy) with a network ACL. | available |
| `/llm-audit-traversal` | Review code that writes files using names/paths parsed from LLM output for path traversal and indirect prompt-injection sinks | Review code that writes files using names/paths parsed from LLM output for path traversal and indirect prompt-injection sinks | available |
| `/mcp-audit` | Audit an HTTP-exposed MCP server (FastMCP/streamable-http) reading from a database — checks bind address, authentication, read-only enforcement at the connection layer, and error-detail leakage. | Audit an HTTP-exposed MCP server (FastMCP/streamable-http) reading from a database — checks bind address, authentication, read-only enforcement at the connection layer, and error-detail leakage. | available |
| `/security-harden-proxy` | Use when building a service or sidecar that calls an authenticated upstream API (Bearer token, API key) and relays results, to prevent the credential or full URL from leaking into logs or client responses | Use when building a service or sidecar that calls an authenticated upstream API (Bearer token, API key) and relays results, to prevent the credential or full URL from leaking into logs or client responses | available |
| `/security-refute-findings` | Adversarially verify candidate security findings to cut false positives before reporting, via attacker/victim privilege-boundary analysis and diff-anchoring; emphasizes reframing removed/delegated controls. See security-triage-findings for the broad refutation-gate catalog. | Adversarially verify candidate security findings to cut false positives before reporting, via attacker/victim privilege-boundary analysis and diff-anchoring; emphasizes reframing removed/delegated controls. | available |
| `/security-review-diff` | Use when asked to "review this change/diff for security vulnerabilities" — applies a disciplined source→sink method that reports only real security findings, not robustness or best-practice nits. Generates findings from a diff; to verify/refute an existing candidate list, use security-refute-findings. | Use when asked to "review this change/diff for security vulnerabilities" — applies a disciplined source→sink method that reports only real security findings, not robustness or best-practice nits. | available |
| `/security-triage-findings` | Adversarially verify candidate security findings before reporting, refuting any where the attacker is the only victim or the diff does not introduce the sink. Broad refutation-gate catalog; see security-refute-findings for the removed/delegated-control reframing variant. | Adversarially verify candidate security findings before reporting, refuting any where the attacker is the only victim or the diff does not introduce the sink. | available |

### Planning & Specs

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/data-wire-field` | Use when adding a field to a data model, snapshot row, or context object that a downstream component (LLM prompt, API response, report) is supposed to consume — verifies the population site exists, not just the schema. | Use when adding a field to a data model, snapshot row, or context object that a downstream component (LLM prompt, API response, report) is supposed to consume — verifies the population site exists, not just the schema. | available |
| `/design-validate` | After drafting a design but before writing the spec, validate the debatable/assumption-laden choices with targeted external research | After drafting a design but before writing the spec, validate the debatable/assumption-laden choices with targeted external research | available |
| `/issue-prep-auto` | Triage/groom/prep a single issue for the auto-dev loop — apply the `auto-dev` label when ready, else tighten scope and draft clarifying questions. Use before issue-dev-auto to assess or make-ready an issue for autonomous development. | Triage/groom/prep a single issue for the auto-dev loop — apply the `auto-dev` label when ready, else tighten scope and draft clarifying questions. | available |
| `/issue-prioritize` | Fetch open issues from GitHub, GitLab, or Linear, score them by impact/urgency/readiness/risk, and recommend the top issues to address next. Analysis-only — no mutations. | Fetch open issues from GitHub, GitLab, or Linear, score them by impact/urgency/readiness/risk, and recommend the top issues to address next. | available |
| `/issue-triage` | Comprehensive Linear issue audit: validate prioritization, identify duplicates and overlapping issues, detect stale/obsolete issues, produce clean actionable backlog | Comprehensive Linear issue audit: validate prioritization, identify duplicates and overlapping issues, detect stale/obsolete issues, produce clean actionable backlog | available |
| `/plan-manage` | Manage plan lifecycle in ~/.claude/.plans with create, review, execute, archive, and abandon flows, including optional parallel-agent orchestration. | Manage plan lifecycle in ~/. | available |
| `/premise-verify` | Verify a load-bearing assumption before building on it. Use when a spec, skill, hook, parser, or config depends on an assumed CLI subcommand/flag, tool capability, env var, API response field/date semantics, or container image runtime contract. | Use when a spec, skill, hook, parser, or config depends on an assumed CLI subcommand/flag, tool capability, env var, API response field/date semantics, or container image runtime contract. | available |
| `/spec-audit-tasks` | After an implement step, audit that every task in the task list was genuinely completed — catch skipped tasks, stubbed work, missing tests, or unimplemented spec requirements. Works with speckit (tasks.md) and superpowers (tasks embedded in the plan) layouts; auto-discovers or takes explicit paths. Runs automatically as the speckit after_implement hook; invoke directly to re-audit. | After an implement step, audit that every task in the task list was genuinely completed — catch skipped tasks, stubbed work, missing tests, or unimplemented spec requirements. | available |
| `/spec-decide-tradeoffs` | Use when a design choice has multiple valid options — produce a dimension-by-dimension trade-off table (fidelity, accuracy, scale, maintainability), justify one recommendation against long-term failure modes, and record it in the spec. Works with speckit and superpowers layouts. | Use when a design choice has multiple valid options — produce a dimension-by-dimension trade-off table (fidelity, accuracy, scale, maintainability), justify one recommendation against long-term failure modes, and record it in the spec. | available |
| `/spec-review` | Cross-reference spec/plan/tasks artifacts for internal consistency via the parallel-agent panel (excluding the author); deduped findings list. Analysis-only, never edits. Speckit and superpowers layouts; auto-discovers or takes explicit paths. | Cross-reference spec/plan/tasks artifacts for internal consistency via the parallel-agent panel (excluding the author); deduped findings list. | available |

### Skill Authoring

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/ai-hooks-integration` | Integrate lifecycle hooks across AI coding tools (Claude Code, Gemini CLI, Cursor, OpenCode) — adding/installing hooks, OpenCode plugins, auto-format/notify/security policies, or wrapping CLIs without a hooks API. Covers PreToolUse/PostToolUse and HTTP/prompt/agent/async hooks. | Integrate lifecycle hooks across AI coding tools (Claude Code, Gemini CLI, Cursor, OpenCode) — adding/installing hooks, OpenCode plugins, auto-format/notify/security policies, or wrapping CLIs without a hooks API. | available |
| `/prompt-optimize` | Use when a user asks to create, optimize, refactor, or harden a prompt into a production-ready skill template. Refactors raw prompts into a fixed XML-schema payload, stripping conversational preamble and injecting absolute-path, idempotency, and runtime guardrails. | Use when a user asks to create, optimize, refactor, or harden a prompt into a production-ready skill template. | available |
| `/skill-evolve` | Turn SkillClaw-evolved skills into a reviewed PR into .skillshare/skills/. Dry-run by default; --apply opens one PR with one commit per skill. Requires --enable-skillclaw and claude CLI login. Never writes source of truth directly — all changes go through PR review. | Turn SkillClaw-evolved skills into a reviewed PR into . | available |

### CI/CD, Testing & Quality

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/a11y-audit` | Focused accessibility audit against WCAG 2.2 AA standards. Checks ARIA best practices, semantic HTML, focus management, color contrast, keyboard navigation, skip links, alt text, form labels, and error announcements. | Focused accessibility audit against WCAG 2. | available |
| `/ai-code-audit` | Seven-pass audit of a codebase for AI-generation defects (architecture, async/state, error handling, security, logic, quality, iteration): evidence-traced, severity-classified, cross-verified findings. Use for "audit this codebase", "find vibe-coding/AI antipatterns". | Seven-pass audit of a codebase for AI-generation defects (architecture, async/state, error handling, security, logic, quality, iteration): evidence-traced, severity-classified, cross-verified findings. | available |
| `/ci-diagnose-drift` | Diagnose lint/format failures that only appear in CI (pass locally) by finding where CI overrides the repo's committed linter config, then verify the fix at the annotation level | Diagnose lint/format failures that only appear in CI (pass locally) by finding where CI overrides the repo's committed linter config, then verify the fix at the annotation level | available |
| `/ci-reproduce-failure` | Use when a CI job fails but the run's logs are gated ("still in progress") or hard to read — pinpoint the failing step via the jobs API and reproduce that step's commands locally from the workflow file. | Use when a CI job fails but the run's logs are gated ("still in progress") or hard to read — pinpoint the failing step via the jobs API and reproduce that step's commands locally from the workflow file. | available |
| `/ci-setup` | Configure CI/CD pipelines for a target repository based on detected languages, project structure, and hosting platform (GitHub Actions or GitLab CI). | Configure CI/CD pipelines for a target repository based on detected languages, project structure, and hosting platform (GitHub Actions or GitLab CI). | available |
| `/data-validate-live` | Validate data-ingestion, parsing, ETL, or API-integration code against real/live data — smoke pass, pre-merge gate, or post-unit-test. Surfaces fixture-blind bugs (free-text numerics, dedup-key collisions, falsy-zero) that fixtures hide. | Validate data-ingestion, parsing, ETL, or API-integration code against real/live data — smoke pass, pre-merge gate, or post-unit-test. | available |
| `/go-refactor` | Perform security, architecture, and quality analysis for Go codebases and return a prioritized, actionable refactoring roadmap. | Perform security, architecture, and quality analysis for Go codebases and return a prioritized, actionable refactoring roadmap. | available |
| `/node-refactor` | Perform security, architecture, and quality analysis for Node.js/TypeScript codebases and return a prioritized, actionable refactoring roadmap. | Perform security, architecture, and quality analysis for Node. | available |
| `/performance-check` | Frontend performance audit: bundle size analysis, Core Web Vitals targets, lazy loading, image optimization, caching strategy, code splitting, and render-blocking resource detection. | Frontend performance audit: bundle size analysis, Core Web Vitals targets, lazy loading, image optimization, caching strategy, code splitting, and render-blocking resource detection. | available |
| `/project-verify` | Run linters, unit tests, and security scans in parallel for a target project. Auto-detects language from project files and runs the appropriate tool chain. Produces a unified quality report with pass/warn/fail per category. | Run linters, unit tests, and security scans in parallel for a target project. | available |
| `/python-refactor` | Perform security, architecture, and quality analysis for Python codebases and return a prioritized, actionable refactoring roadmap. | Perform security, architecture, and quality analysis for Python codebases and return a prioritized, actionable refactoring roadmap. | available |
| `/shell-refactor` | Perform security and quality analysis for Bash/Shell scripts and produce a prioritized refactor plan with risk and effort guidance. | Perform security and quality analysis for Bash/Shell scripts and produce a prioritized refactor plan with risk and effort guidance. | available |
| `/smoke-manage` | Append, run, and maintain declarative tiered E2E smoke tests (UI/API/CLI) per app. Use after shipping a feature to add coverage, to gate a PR (Lite run → JUnit + exit code), or for nightly Full runs. Catalog lives in smoke-catalog/<app>.yaml. | Append, run, and maintain declarative tiered E2E smoke tests (UI/API/CLI) per app. | available |
| `/terraform-refactor` | Perform security, modularity, and quality analysis for Terraform/OpenTofu IaC codebases and return a prioritized, actionable refactoring roadmap. | Perform security, modularity, and quality analysis for Terraform/OpenTofu IaC codebases and return a prioritized, actionable refactoring roadmap. | available |
| `/test-pin-bug` | Use when testing a known bug or placeholder you are NOT fixing now — make the assertion tolerate the post-fix output too, so the fix doesn't break the suite later. Anchor the real invariant separately. | Use when testing a known bug or placeholder you are NOT fixing now — make the assertion tolerate the post-fix output too, so the fix doesn't break the suite later. | available |
| `/test-vary-fixtures` | Use when writing/debugging unit tests for z-score, standard-deviation, normalization, or surge/ratio functions — flat fixture data collapses the statistic to zero and silently fails assertions. Build baselines with real variance. | Use when writing/debugging unit tests for z-score, standard-deviation, normalization, or surge/ratio functions — flat fixture data collapses the statistic to zero and silently fails assertions. | available |
| `/ux-review` | Automated UX audit covering accessibility (WCAG 2.2), responsive design, performance budgets (Core Web Vitals), progressive enhancement, color contrast, keyboard navigation, and screen reader compatibility. | Automated UX audit covering accessibility (WCAG 2. | available |

### Infrastructure & Config

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/api-optimize-bulk` | Before running N sequential per-entity API calls, check vendor docs and client source for a bulk/aggregate endpoint that replaces them with one call | Before running N sequential per-entity API calls, check vendor docs and client source for a bulk/aggregate endpoint that replaces them with one call | available |
| `/cache-warm-oob` | Use when an in-process HTTP client stalls at scale (thousands of sequential calls) but the endpoint itself is healthy — warm the cache out-of-band with a hard-deadline tool, then run the job cache-only. | Use when an in-process HTTP client stalls at scale (thousands of sequential calls) but the endpoint itself is healthy — warm the cache out-of-band with a hard-deadline tool, then run the job cache-only. | available |
| `/cli-audit-help` | Use when adding or auditing --help/--version/usage on a script or CLI — the help path must succeed before any config/state/dependency lookup, verified in a clean environment (empty HOME, fresh clone, CI), not just a pre-configured machine. | Use when adding or auditing --help/--version/usage on a script or CLI — the help path must succeed before any config/state/dependency lookup, verified in a clean environment (empty HOME, fresh clone, CI), not just a pre-configured machine. | available |
| `/config-audit` | Verify cross-platform configuration consistency, check symlink integrity, and detect config drift between Claude, Cursor, Gemini, and Codex platforms. | Verify cross-platform configuration consistency, check symlink integrity, and detect config drift between Claude, Cursor, Gemini, and Codex platforms. | available |
| `/config-debug-substitution` | Use when a containerized app crash-loops or errors on "variable not found"/empty-value despite the orchestrator validating fine — the app does its OWN ${VAR} substitution on mounted config, separate from compose/k8s interpolation. | Use when a containerized app crash-loops or errors on "variable not found"/empty-value despite the orchestrator validating fine — the app does its OWN ${VAR} substitution on mounted config, separate from compose/k8s interpolation. | available |
| `/config-validate-native` | Use before deploying any app that parses its own config file (Glance, nginx, Traefik, Prometheus, Terraform, etc.) — validate with the application's OWN parser, not a generic linter, because generic linting passes configs the app rejects. | Use before deploying any app that parses its own config file (Glance, nginx, Traefik, Prometheus, Terraform, etc. | available |
| `/data-design-ingestion` | Use when designing a local table that caches records fetched from an external feed — choose append-only+dedup vs full-replace based on whether the upstream data is immutable history or re-published-in-full. | Use when designing a local table that caches records fetched from an external feed — choose append-only+dedup vs full-replace based on whether the upstream data is immutable history or re-published-in-full. | available |
| `/deploy-diagnose-drift` | Use when a deployed/live environment is missing expected state (symlinks, files, config) after bootstrap/deploy — even on already-bootstrapped machines — to classify the gap (incomplete run, deployer bug, preserve-on-existing drop) and fix the source of truth. | Use when a deployed/live environment is missing expected state (symlinks, files, config) after bootstrap/deploy — even on already-bootstrapped machines — to classify the gap (incomplete run, deployer bug, preserve-on-existing drop) and fix the source of truth. | available |
| `/deploy-retire-component` | Retire/remove a component after migration or uninstall — verify the artifact is gone, nothing will respawn it, and the new state landed. Covers Unix daemons (launchd/systemd), migrated tool runtimes (stale daemons, sockets), and plugins/MCP servers. | Retire/remove a component after migration or uninstall — verify the artifact is gone, nothing will respawn it, and the new state landed. | available |
| `/docker-probe-internal` | Use to test or debug a service that only listens on an internal Docker network (no host port, no public route) when host curl/wget is unavailable or blocked | Use to test or debug a service that only listens on an internal Docker network (no host port, no public route) when host curl/wget is unavailable or blocked | available |
| `/llm-invoke-stdin` | Use when a script needs to call an LLM/agent CLI (claude -p, gemini -p, agy -p) as a step — pipe the prompt via stdin behind an injectable seam so it is ARG_MAX-safe and testable offline. | Use when a script needs to call an LLM/agent CLI (claude -p, gemini -p, agy -p) as a step — pipe the prompt via stdin behind an injectable seam so it is ARG_MAX-safe and testable offline. | available |
| `/pass-cli` | Retrieve credentials (passwords, API keys, tokens, SSH keys) from Proton Pass via pass-cli. Use when a task needs a login/secret or user mentions Proton Pass, a vault, or "get the credentials/token for X". Covers PAT session setup and expired-session recovery. | Use when a task needs a login/secret or user mentions Proton Pass, a vault, or "get the credentials/token for X". | available |
| `/process-diagnose-stall` | Use when a long-running background job (data pipeline, batch fetch, analysis run) stops making progress — measure its resource signature to classify the stall instead of guessing fixes. | Use when a long-running background job (data pipeline, batch fetch, analysis run) stops making progress — measure its resource signature to classify the stall instead of guessing fixes. | available |
| `/project-scaffold` | Initialize new projects with language-specific quality gates, linting configs, test frameworks, CI/CD templates, and Manifest integration. | Initialize new projects with language-specific quality gates, linting configs, test frameworks, CI/CD templates, and Manifest integration. | available |
| `/shell-audit-errexit` | Use when a bash script under `set -euo pipefail` aborts in production but passes tests — audit helpers and sourced libs for non-`$()` control-flow triggers (trailing `&&`, stdin-drain, SIGPIPE, `((i++))`). Complements shell-audit-pipefail. | Use when a bash script under `set -euo pipefail` aborts in production but passes tests — audit helpers and sourced libs for non-`$()` control-flow triggers (trailing `&&`, stdin-drain, SIGPIPE, `((i++))`). | available |
| `/shell-audit-pipefail` | Audit bash scripts using set -euo pipefail for silent-abort risks in $() command substitutions that parse empty or malformed input. Complements shell-audit-errexit (non-$() control-flow triggers). | Audit bash scripts using set -euo pipefail for silent-abort risks in $() command substitutions that parse empty or malformed input. | available |
| `/version-pin` | Enforce hashed version pins in requirements.txt, docker-compose.yaml, and Dockerfiles — detects loose refs (latest, missing hash, unbounded range), resolves version+hash via native package managers, auto-fixes or warns on save hook. Per-entry bypass supported. | Enforce hashed version pins in requirements. | available |

### Meta & Orchestration

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/antipattern-detect` | Auto-triggered skill that analyzes linting failures, test results, and code review feedback to detect recurring antipatterns. Stores findings in knowledge_base.yml (YAML source of truth) via learning_capture.sh. | Auto-triggered skill that analyzes linting failures, test results, and code review feedback to detect recurring antipatterns. | available |
| `/code-audit` | Auto-trigger on security-sensitive code (auth, crypto, secrets, input validation), large files (>500 lines), or complex files (>10 functions/>5 classes). Gives code-audit and security feedback without blocking user flow. | Auto-trigger on security-sensitive code (auth, crypto, secrets, input validation), large files (>500 lines), or complex files (>10 functions/>5 classes). | available |
| `/env-check` | Verify CLI tool availability, authentication status, config syntax, MCP connectivity, and symlink integrity for the Manifest environment. | Verify CLI tool availability, authentication status, config syntax, MCP connectivity, and symlink integrity for the Manifest environment. | available |
| `/graphify` | Map a codebase, docs, or GitHub repo into a queryable knowledge graph (graphify CLI): graph.html, GRAPH_REPORT.md, graph.json. Use to understand large or unfamiliar code, or answer "what connects X to Y?". | Map a codebase, docs, or GitHub repo into a queryable knowledge graph (graphify CLI): graph. | available |
| `/help` | Use when you need to find the right Manifest command for a task — searches and lists every command by category with a one-line description and when-to-use cue, flagging ones unavailable here. Read-only; never runs or modifies. | Use when you need to find the right Manifest command for a task — searches and lists every command by category with a one-line description and when-to-use cue, flagging ones unavailable here. | available |
| `/learning-capture` | Capture structured lessons learned after major tasks. Categories: pattern, antipattern, tool discovery, configuration insight. Stores in ~/.claude/config/knowledge_base.yml and queries existing learnings. | Capture structured lessons learned after major tasks. | available |
| `/memory-compress` | Compress or summarize memory/log entries — distill a session/transcript into a dated one-line entry, or losslessly compress/rotate existing memory entries (daily summary, developer-shorthand rewrite, one-sentence log line) with zero information loss. | Compress or summarize memory/log entries — distill a session/transcript into a dated one-line entry, or losslessly compress/rotate existing memory entries (daily summary, developer-shorthand rewrite, one-sentence log line) with zero information loss. | available |
| `/metrics-report` | Visualize agent efficiency metrics: task completion rates, common error patterns, consensus scores, and model usage distribution. Reads from .claude/.agent_outputs/ logs and outputs markdown tables and summaries. | Visualize agent efficiency metrics: task completion rates, common error patterns, consensus scores, and model usage distribution. | available |
| `/session-checkpoint` | Create a compact checkpoint summary of the current session so work can continue reliably when context usage is high. | Create a compact checkpoint summary of the current session so work can continue reliably when context usage is high. | available |
| `/token-benchmark` | Measure token overhead and quality delta from Manifest config across Claude, Gemini CLI, and Antigravity CLI using MMLU/HumanEval/HellaSwag/TruthfulQA prompts before/after manifest context injection; regenerates docs/TOKEN_BENCHMARK.md. | Measure token overhead and quality delta from Manifest config across Claude, Gemini CLI, and Antigravity CLI using MMLU/HumanEval/HellaSwag/TruthfulQA prompts before/after manifest context injection; regenerates docs/TOKEN_BENCHMARK. | available |
| `/token-conserve` | Switch the current session into terse, surgical, clarify-first mode to cut token usage. Invoke when responses are verbose, during long refactors, or to conserve budget. Opt-in session mutator — re-invoke if it wears off. | Switch the current session into terse, surgical, clarify-first mode to cut token usage. | available |

### Uncategorized

| Command | Description | When to use | Status |
|---------|-------------|-------------|--------|
| `/automation-rework-breakeven` | Use when deciding whether a more-thorough-but-costlier automation or skill version is worth it — separate correctness from cost, model net tokens as rework-avoided minus extra spend, and measure the rework cost empirically instead of assuming it. | Use when deciding whether a more-thorough-but-costlier automation or skill version is worth it — separate correctness from cost, model net tokens as rework-avoided minus extra spend, and measure the rework cost empirically instead of assuming it. | available |
| `/code-to-design` | Convert frontend code (Vite, React, etc.) to a Stitch Design by chaining HTML extraction, design-system extraction, and upload. ALWAYS use when the user wants to save/migrate/upload an existing web app or React components into Stitch. | use when the user wants to save/migrate/upload an existing web app or React components into Stitch. | available |
| `/deploy-reconcile` | Review what Manifest deployed into the assistant homes (~/.claude + mirrors) versus what the project would deploy, listing orphaned deployed items KEEP or REMOVE. Preview by default; opt-in removal is recoverable (timestamped backup, never hard-delete). | Review what Manifest deployed into the assistant homes (~/. | available |
| `/design-md` | Analyze Stitch projects and synthesize a semantic design system into DESIGN.md files | Analyze Stitch projects and synthesize a semantic design system into DESIGN. | available |
| `/enhance-prompt` | Transforms vague UI ideas into polished, Stitch-optimized prompts. Enhances specificity, adds UI/UX keywords, injects design system context, and structures output for better generation results. | Transforms vague UI ideas into polished, Stitch-optimized prompts. | available |
| `/extract-design-md` | Extract a Stitch-compatible DESIGN.md design system directly from frontend source (React, Vue, Svelte, Angular, HTML/CSS) — components, stylesheets, tokens, themes. Use to reverse-engineer or audit a project's design system. | Extract a Stitch-compatible DESIGN. | available |
| `/extract-static-html` | Extract self-contained static HTML from a built web app or React components by inlining CSS and images. Use to capture a UI state, share a static page, or prep assets for Stitch upload. | Extract self-contained static HTML from a built web app or React components by inlining CSS and images. | available |
| `/false-green-check-audit` | Use when writing or reviewing a health-check, status, validation, or CI gate that can SKIP verifying something (missing credential, unsupported provider, absent tool) — ensure a skipped/unverifiable check never renders as a green pass, and add a verification path through the credential or channel the user actually uses (e.g. an OAuth CLI, not an assumed API key). | Use when writing or reviewing a health-check, status, validation, or CI gate that can SKIP verifying something (missing credential, unsupported provider, absent tool) — ensure a skipped/unverifiable check never renders as a green pass, and add a verification path through the credential or channel the user actually uses (e. | available |
| `/generate-design` | Generate new Stitch screens from text/images, edit existing screens with prompts and design tokens, and create design variants via the Stitch MCP server. | Generate new Stitch screens from text/images, edit existing screens with prompts and design tokens, and create design variants via the Stitch MCP server. | available |
| `/lifecycle-run` | Drive a feature/issue through the codified state-gated lifecycle (specify→…→verify) with hard phase-gating and a smoke-test Verify gate; entry is a ticket URL/issue key. | Drive a feature/issue through the codified state-gated lifecycle (specify→…→verify) with hard phase-gating and a smoke-test Verify gate; entry is a ticket URL/issue key. | available |
| `/manage-design-system` | Manage design systems in Stitch via MCP: retrieve assets, create/update design systems, and apply them to screens. | Manage design systems in Stitch via MCP: retrieve assets, create/update design systems, and apply them to screens. | available |
| `/pr-smoke` | Full Manifest regression (CI mirror: shellcheck, yamllint, bats, pytest) plus a deployed-env smoke pass — the post-PR gate. Use when a PR opens or merges: "regression test the PR", "did the merge break anything", "verify main is still green". Whole-repo verdict; prefer over verify or env-check. | Use when a PR opens or merges: "regression test the PR", "did the merge break anything", "verify main is still green". | available |
| `/react-components` | Converts Stitch designs into modular Vite/React components, or syncs existing React components with the latest Stitch designs, using networked fetch and AST-based validation. | Converts Stitch designs into modular Vite/React components, or syncs existing React components with the latest Stitch designs, using networked fetch and AST-based validation. | available |
| `/react-native` | Convert Stitch HTML designs to React Native components, or sync existing native components with the latest Stitch designs, using StyleSheet. | Convert Stitch HTML designs to React Native components, or sync existing native components with the latest Stitch designs, using StyleSheet. | available |
| `/react-vite-dashboard` | Convert Stitch designs into production React + Vite dashboards with TanStack Query, accessible tokens from DESIGN.md, and Web3-ready patterns (ethers/viem). | Convert Stitch designs into production React + Vite dashboards with TanStack Query, accessible tokens from DESIGN. | available |
| `/remotion` | Generate walkthrough videos from Stitch projects using Remotion with smooth transitions, zooming, and text overlays | Generate walkthrough videos from Stitch projects using Remotion with smooth transitions, zooming, and text overlays | available |
| `/shadcn-ui` | Expert guidance for integrating and building applications with shadcn/ui components, including component discovery, installation, customization, and best practices. | Expert guidance for integrating and building applications with shadcn/ui components, including component discovery, installation, customization, and best practices. | available |
| `/spec-implement-loop` | Critic-gated implementation (CDDL) of a completed spec+plan — speckit feature dir or superpowers design doc. Two critics gate clarification, then an implementer iterates under project verification until dual structured approval stages the changes. Never commits or pushes. | Critic-gated implementation (CDDL) of a completed spec+plan — speckit feature dir or superpowers design doc. | available |
| `/stitch-loop` | Teaches agents to iteratively build websites using Stitch with an autonomous baton-passing loop pattern | Teaches agents to iteratively build websites using Stitch with an autonomous baton-passing loop pattern | available |
| `/taste-design` | Generates agent-friendly DESIGN.md files for Google Stitch enforcing premium, anti-generic UI standards — strict typography, calibrated color, asymmetric layouts, micro-motion. | Generates agent-friendly DESIGN. | available |
| `/upload-to-stitch` | Upload local assets (images, mockups, HTML, design markdown) to a Stitch project. ALWAYS use when visual assets or design docs need uploading, especially when direct MCP calls fail/truncate on base64 token limits. | use when visual assets or design docs need uploading, especially when direct MCP calls fail/truncate on base64 token limits. | available |

<!-- END GENERATED COMMANDS -->
