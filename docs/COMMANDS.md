# Commands Guide

> Building custom commands for Claude Code with Manifest

**Last Updated**: 2026-02-04
**Audience**: Command developers, advanced users
**Prerequisites**: Manifest installed, basic understanding of Markdown and Bash

---

## Table of Contents

1. [What Are Commands](#what-are-commands)
2. [Command Structure](#command-structure)
3. [Command Patterns](#command-patterns)
4. [Building State Machine Commands](#building-state-machine-commands)
5. [Parallel Agent Integration](#parallel-agent-integration)
6. [Error Handling](#error-handling)
7. [Testing Commands](#testing-commands)
8. [Examples](#examples)

---

## What Are Commands

Commands are markdown files that define reusable workflows for Claude Code. They enable:

- **Complex multi-step operations** (deployments, migrations)
- **Automated workflows** (GitHub issue management)
- **Architecture analysis** (event tracing, API mapping)
- **Project management** (commit pipelines, PR creation)

**Location**: `.claude/commands/`

**Invocation**: Users run commands with `/command-name` in Claude Code.

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

- `/docs-diagrams` - Generate Mermaid diagrams
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

- `/project-commit` - Full commit pipeline (regenerate docs, pull, pre-commits, commit, push)
- `/issue-process` - Process GitHub issue
- `/full-deployment-pipeline` - Deploy with validation

**Tool Usage**: Read + Write (Bash, Edit, Write, Skill for invoking other commands)

**Example Structure** (`/project-commit`):

1. Phase 1: Documentation Generation (`/docs-diagrams`, `/docs-improve`, `/docs-readme`)
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

**Pattern Documentation**: See [Command State Machine Pattern](../templates/patterns/command-state-machine.md)

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
~/.claude/scripts/parallel_agent.sh --json --full-output --validate --timeout 600 \
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
result=$(~/.claude/scripts/parallel_agent.sh --json --validate --review "$file")

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

**File**: `.claude/commands/count-todos.md`

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

**File**: `.claude/commands/create-feature-branch.md`

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

- [Command State Machine Pattern](../templates/patterns/command-state-machine.md) - Detailed pattern guide
- [Full Deployment Pipeline](../templates/commands/full-deployment-pipeline.md) - Complete example
- [GitHub Workflow Commands](../templates/github-workflow/) - Issue management commands
- [Configuration Guide](./CONFIGURATION.md) - Parallel agent settings
- [Troubleshooting](./TROUBLESHOOTING.md) - Common command issues

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
