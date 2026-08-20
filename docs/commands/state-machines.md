# State-Machine Commands

> Phased commands, the deployment pipeline, and parallel-agent integration.

**Last Updated**: 2026-08-20

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

---

[← Commands Guide](../COMMANDS.md)
