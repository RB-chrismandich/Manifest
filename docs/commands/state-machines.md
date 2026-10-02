# State-Machine Commands
>
> Phased commands, deployment pipelines, and OMP-native task batches.

**Last Updated**: 2026-09-12

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
Phase 3: Validate Plan (risk-gated independent review)
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
| 3. Validate Plan | ✅ pass | 1m 8s | Parent reviewed worker evidence |
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

## OMP Task-Batch Integration

risk-based independent review follows the five-condition gate below.

Commands may use OMP to decompose genuinely independent workload units. That is
not independent review. Use one capable reviewing agent by default; add
independent review only for a trust-boundary change, destructive behavior, broad
compatibility or deployment change, conflicting evidence or unresolved
uncertainty, or a codebase-wide investigation with genuinely independent
tracks. File, package, module, language, keyword, and independent-unit counts
never trigger independent review.

### Integration Pattern

````markdown
## OMP Task-Batch Integration

This command uses workload fan-out only when ready units are genuinely
independent. It uses independent review only when the five-condition risk gate
above applies.

When independently reviewing:
1. Record `review_mode` and `escalation_reason`.
2. Submit bounded review concerns in one OMP `task` call.
3. Record one exact command/result for each applicable check; an unavailable
   check records `unavailable_reason`, never a passing result.
4. Validate and aggregate evidence in the parent. Keep mutations sequential.
````

---

---

[← Commands Guide](../COMMANDS.md)
