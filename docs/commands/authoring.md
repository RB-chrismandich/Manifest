# Authoring a Command

> What a command is, how it is structured, and the common patterns.

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

---

[← Commands Guide](../COMMANDS.md)
