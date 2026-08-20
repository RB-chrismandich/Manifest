# Error Handling & Testing

> Failure paths, recovery, and how to test a command before shipping it.

**Last Updated**: 2026-08-20

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

---

[← Commands Guide](../COMMANDS.md)
