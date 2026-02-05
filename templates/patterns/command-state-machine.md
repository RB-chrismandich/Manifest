# Command State Machine Pattern

> Build robust multi-phase commands with error recovery and retry logic

**Pattern Type**: Command Design
**Complexity**: Intermediate
**Use Cases**: Deployments, CI/CD pipelines, complex workflows
**Reference**: Based on cookedbooks `project-commit.md`

---

## Overview

The **Command State Machine Pattern** structures complex commands as explicit state machines with:
- **Phases**: Sequential stages with clear boundaries
- **Validation Gates**: Each phase must succeed before next begins
- **Error Recovery**: Automatic retry with backoff
- **Rollback Support**: Clean failure handling
- **Progress Reporting**: Summary tables showing phase results

---

## When to Use This Pattern

### ✅ Use State Machines For

1. **Multi-step processes** with dependencies
   - Deployments (test → build → deploy → verify)
   - Migrations (backup → migrate → validate → cleanup)
   - CI/CD pipelines (lint → test → build → publish)

2. **Operations requiring rollback**
   - Database schema changes
   - Infrastructure updates
   - Service deployments

3. **Long-running tasks** needing progress tracking
   - Data processing pipelines
   - Batch operations
   - System initialization

### ❌ Don't Use State Machines For

1. **Simple single-step commands**
   - File reads, single queries, basic analysis

2. **Purely informational commands**
   - Documentation generation, status checks

3. **Commands with no failure modes**
   - Read-only operations

---

## Pattern Structure

### 1. Phase Definition

Each phase has:
- **Name**: Clear, action-oriented (e.g., "Run Tests")
- **Success Criteria**: How to know phase passed
- **On Failure**: What to do if phase fails
- **Retry Policy**: Whether/how to retry

**Template**:
```markdown
## Command Phases

Execute these phases **in order**. Each phase must succeed before proceeding to the next. If a phase fails, attempt to fix the issue up to **N times** before stopping and reporting the failure to the user.

### Phase 1: [Phase Name]

[Description of what this phase does]

**Success Criteria**:
- [ ] [Criterion 1]
- [ ] [Criterion 2]

**On Failure**:
- [Action to take]
- [Retry policy]

**Example**:
```bash
[command to run]
```

### Phase 2: [Next Phase]

[...]
```

---

### 2. Error Recovery Strategies

#### Strategy 1: Automatic Retry with Backoff

```markdown
**On Failure**:
- Retry up to 2 times with 5-second delay
- If still failing, report error and stop
```

**Implementation Pattern**:
```bash
for attempt in {1..3}; do
  if run_phase_2; then
    break
  elif [[ $attempt -lt 3 ]]; then
    echo "Phase 2 failed (attempt $attempt/3), retrying in 5s..."
    sleep 5
  else
    echo "Phase 2 failed after 3 attempts"
    exit 1
  fi
done
```

---

#### Strategy 2: Selective Retry by Error Type

```markdown
**On Failure**:
- If network error: Retry once after 10s
- If validation error: Fix issue and retry (max 2x)
- If fatal error: Stop immediately
```

**Implementation Pattern**:
```bash
if ! run_phase; then
  if [[ "$error_type" == "network" ]]; then
    sleep 10
    run_phase
  elif [[ "$error_type" == "validation" ]]; then
    fix_issue
    run_phase
  else
    echo "Fatal error, stopping"
    exit 1
  fi
fi
```

---

#### Strategy 3: User Confirmation on Failure

```markdown
**On Failure**:
- Show error details
- Ask user: "Retry? Skip? Abort?"
- Proceed based on user choice
```

**Implementation Pattern** (using AskUserQuestion):
```markdown
Use AskUserQuestion tool:
- Question: "Phase 2 failed with error: $ERROR. What would you like to do?"
- Options:
  - "Retry phase 2" (attempt again)
  - "Skip phase 2 and continue" (proceed to phase 3)
  - "Abort command" (stop here)
```

---

#### Strategy 4: Automatic Rollback

```markdown
**On Failure**:
- Roll back phase 2 changes
- Restore phase 1 state
- Report rollback status
```

**Implementation Pattern**:
```bash
# Save state before phase
save_state "pre_phase_2"

if ! run_phase_2; then
  echo "Phase 2 failed, rolling back..."
  restore_state "pre_phase_2"
  exit 1
fi
```

---

### 3. Success Criteria Patterns

#### Pattern A: Command Exit Code

```markdown
**Success Criteria**:
- [ ] Command exits with code 0
```

```bash
if command_here; then
  phase_passed=true
else
  phase_passed=false
fi
```

---

#### Pattern B: File/Output Verification

```markdown
**Success Criteria**:
- [ ] Output file exists and is non-empty
- [ ] Output contains "SUCCESS" marker
```

```bash
if [[ -s "$output_file" ]] && grep -q "SUCCESS" "$output_file"; then
  phase_passed=true
else
  phase_passed=false
fi
```

---

#### Pattern C: Multiple Conditions (AND)

```markdown
**Success Criteria**:
- [ ] All tests pass (pytest exit code 0)
- [ ] Coverage >= 80%
- [ ] No linting errors
```

```bash
tests_pass=false
coverage_ok=false
lint_ok=false

pytest && tests_pass=true
coverage report --fail-under=80 && coverage_ok=true
ruff check . && lint_ok=true

if [[ "$tests_pass" == true && "$coverage_ok" == true && "$lint_ok" == true ]]; then
  phase_passed=true
else
  phase_passed=false
fi
```

---

#### Pattern D: Parallel Agent Consensus

```markdown
**Success Criteria**:
- [ ] Parallel agent consensus >= 80%
```

```bash
result=$(~/.claude/scripts/parallel_agent.sh --json --validate --review "$file")
consensus=$(echo "$result" | jq -r '.cross_verification.consensus_score')

if [[ $consensus -ge 80 ]]; then
  phase_passed=true
else
  phase_passed=false
fi
```

---

### 4. Progress Tracking

#### Summary Table Format

At the end of command execution, provide a summary table:

```markdown
## [Command Name] Summary

| Phase | Status | Duration | Notes |
|-------|--------|----------|-------|
| 1. Preparation | ✅ pass | 2s | All files readable |
| 2. Validation | ✅ pass | 15s | Consensus: 85% |
| 3. Execution | ❌ fail | 8s | Network timeout (attempt 2/2) |
| 4. Verification | ⏭️ skipped | - | Previous phase failed |
| 5. Cleanup | ✅ pass | 1s | Temp files removed |

**Overall**: FAILED (Phase 3)
**Total Duration**: 26s
**Next Steps**: Check network connection and retry
```

**Status Icons**:
- ✅ pass - Phase succeeded
- ❌ fail - Phase failed (after retries)
- ⚠️ warn - Phase succeeded with warnings
- ⏭️ skipped - Phase not executed (dependency failed)
- 🔄 retry - Phase retried N times

---

## Complete Example

See: `templates/commands/full-deployment-pipeline.md`

5-phase deployment command demonstrating:
- Sequential phases with dependencies
- Retry logic (2x per phase)
- Rollback on failure
- Summary table output
- Parallel agent validation

---

## Implementation Checklist

When building a state machine command:

### Design Phase
- [ ] Identify all phases (typically 3-7 phases)
- [ ] Define dependencies (which phases depend on others)
- [ ] Choose error recovery strategy per phase
- [ ] Define success criteria per phase
- [ ] Decide retry limits

### Implementation Phase
- [ ] Document phase order at top of command
- [ ] Implement each phase with clear boundaries
- [ ] Add retry logic where appropriate
- [ ] Add rollback logic for destructive operations
- [ ] Track phase status in variables

### Testing Phase
- [ ] Test happy path (all phases pass)
- [ ] Test failure recovery (force each phase to fail)
- [ ] Test retry exhaustion (max retries reached)
- [ ] Test rollback (verify state restored)
- [ ] Test summary table generation

---

## Common Patterns

### Pattern 1: Read-Validate-Execute-Verify (RVEV)

```markdown
Phase 1: Read Configuration
Phase 2: Validate Configuration
Phase 3: Execute Operation
Phase 4: Verify Results
```

**Use For**: Deployments, migrations, infrastructure changes

---

### Pattern 2: Prepare-Process-Publish-Cleanup (PPPC)

```markdown
Phase 1: Prepare Environment
Phase 2: Process Data
Phase 3: Publish Results
Phase 4: Cleanup Temporary Files
```

**Use For**: Data pipelines, batch processing, reporting

---

### Pattern 3: Fetch-Build-Test-Deploy (FBTD)

```markdown
Phase 1: Fetch Latest Code
Phase 2: Build Artifacts
Phase 3: Run Tests
Phase 4: Deploy to Environment
```

**Use For**: CI/CD pipelines, continuous deployment

---

### Pattern 4: Backup-Migrate-Validate-Commit (BMVC)

```markdown
Phase 1: Backup Current State
Phase 2: Run Migration
Phase 3: Validate New State
Phase 4: Commit Changes (or Rollback)
```

**Use For**: Database migrations, schema changes, data transformations

---

## Advanced: Conditional Phase Execution

Some phases may be optional based on context:

```markdown
### Phase 3: Optional Code Generation

**Conditions**: Only run if project contains Protobuf files

**Detection**:
```bash
if find . -name "*.proto" | grep -q .; then
  echo "Protobuf files detected, running code generation..."
  run_phase_3
else
  echo "No Protobuf files, skipping code generation"
fi
```

---

## Advanced: Parallel Phase Execution

Some phases can run in parallel:

```markdown
### Phase 2: Parallel Testing

Run unit tests and integration tests in parallel:

**Implementation**:
```bash
# Start both in background
pytest tests/unit/ > unit_results.txt 2>&1 &
unit_pid=$!

pytest tests/integration/ > integration_results.txt 2>&1 &
integration_pid=$!

# Wait for both
wait $unit_pid
unit_passed=$?

wait $integration_pid
integration_passed=$?

# Check if both passed
if [[ $unit_passed -eq 0 && $integration_passed -eq 0 ]]; then
  phase_passed=true
else
  phase_passed=false
fi
```

---

## Best Practices

### 1. Keep Phases Focused

Each phase should have **one clear responsibility**:
- ✅ Good: "Run unit tests"
- ❌ Bad: "Run tests and deploy if they pass"

### 2. Make Phases Idempotent

Phases should be safe to retry:
- ✅ Good: `mkdir -p temp/` (succeeds even if exists)
- ❌ Bad: `mkdir temp/` (fails if exists)

### 3. Provide Clear Feedback

Users should always know what's happening:
```bash
echo "Phase 2: Running tests..."
pytest
echo "✅ Tests passed"
```

### 4. Document Exit Points

Make it clear when/why command stops:
```markdown
**Exit Points**:
- Phase 2 fails after 2 retries → Exit code 2
- Phase 4 validation fails → Exit code 4
- User aborts during Phase 3 → Exit code 130
```

### 5. Consider Partial Success

Some commands can partially succeed:
```markdown
**Partial Success**: If Phases 1-3 pass but Phase 4 fails, the core work is done but verification failed. User should decide whether to proceed.
```

---

## Integration with Parallel Agents

State machine commands often use parallel agents for validation phases:

```markdown
### Phase 3: Cross-Verify Changes

**Parallel Agent Integration**: CONDITIONAL (only if >100 lines changed)

**Implementation**:
```bash
lines_changed=$(git diff --stat | tail -1 | awk '{print $4}')

if [[ $lines_changed -gt 100 ]]; then
  result=$(~/.claude/scripts/parallel_agent.sh --json --validate \
    --timeout 600 --review "$changed_file")

  consensus=$(echo "$result" | jq -r '.cross_verification.consensus_score')

  if [[ $consensus -ge 80 ]]; then
    echo "✅ Cross-verification passed ($consensus%)"
    phase_passed=true
  else
    echo "⚠️ Cross-verification low consensus ($consensus%)"
    # Ask user whether to proceed
  fi
else
  echo "Changes small (<100 lines), skipping cross-verification"
  phase_passed=true
fi
```

---

## Related Patterns

- **Multi-Agent Orchestration**: Use state machines to coordinate multiple sub-agents
- **Error Recovery**: Detailed strategies for handling failures
- **Progress Reporting**: User feedback during long-running operations

---

## Examples in Manifest

1. `templates/commands/full-deployment-pipeline.md` - Complete deployment example
2. `templates/github-workflow/issue-process.md` - GitHub issue processing
3. `.claude/commands/project-commit.md` - Full commit pipeline (if using cookedbooks pattern)

---

## Further Reading

- [docs/COMMANDS.md](../../docs/COMMANDS.md) - Building Custom Commands
- [templates/commands/](../commands/) - Example commands
- [cookedbooks project-commit.md](https://github.com/ReefBytes/cookedbooks) - Reference implementation
