---
description: Full deployment pipeline with test → build → validate → deploy → verify phases
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion, Task
argument-hint: [environment: staging|production]
---

# Full Deployment Pipeline

Orchestrate a complete deployment cycle with multiple validation gates, automatic rollback, and parallel agent verification. Demonstrates the **Command State Machine Pattern**.

**Pattern**: State Machine (5 phases)
**Complexity**: Advanced
**Use Case**: Production deployments with safety checks

---

## Arguments

- `$ARGUMENTS` - Target environment (`staging` or `production`)
- If not provided, defaults to `staging`

---

## Command Phases

Execute these phases **in order**. Each phase must succeed before proceeding to the next. If a phase fails, attempt to fix the issue up to **2 times** before stopping and reporting the failure to the user.

**Phase Dependencies**:

```
Phase 1 (Test) ─→ Phase 2 (Build) ─→ Phase 3 (Validate) ─→ Phase 4 (Deploy) ─→ Phase 5 (Verify)
     ↓                 ↓                    ↓                    ↓                    ↓
  Required          Required             Required          DESTRUCTIVE           Final Check
```

**Rollback Points**:

- Phase 1-3 failures: No rollback needed (no changes made)
- Phase 4 failure: Automatic rollback to previous version
- Phase 5 failure: Keep deployment, alert team

---

## Phase 1: Run Tests

Run the full test suite to ensure code quality before deployment.

### Success Criteria

- [ ] All unit tests pass (exit code 0)
- [ ] All integration tests pass (exit code 0)
- [ ] Test coverage >= 80%
- [ ] No test timeouts

### On Failure

- Retry up to 2 times (flaky tests)
- If still failing: **STOP** - Do not proceed to build

### Implementation

```bash
# Run unit tests
echo "Running unit tests..."
if ! pytest tests/unit/ --cov --cov-report=term-missing --cov-fail-under=80; then
  echo "❌ Unit tests failed"
  exit 1
fi

# Run integration tests (if dev environment is up)
if docker compose ps | grep -q "Up"; then
  echo "Running integration tests..."
  if ! pytest tests/integration/; then
    echo "❌ Integration tests failed"
    exit 1
  fi
else
  echo "⚠️ Dev environment not running, skipping integration tests"
fi

echo "✅ All tests passed"
```

### Expected Duration

- Unit tests: 30-60s
- Integration tests: 60-120s
- Total: ~2-3 minutes

---

## Phase 2: Build Artifacts

Build deployment artifacts (Docker images, compiled binaries, etc.)

### Success Criteria

- [ ] Build completes without errors
- [ ] Artifacts created and tagged
- [ ] Artifacts uploaded to registry (if applicable)
- [ ] Build size within expected range

### On Failure

- Retry once (network issues)
- If still failing: **STOP** - Check build logs

### Implementation

```bash
# Determine environment
ENVIRONMENT="${ARGUMENTS:-staging}"
VERSION=$(git describe --tags --always)
IMAGE_TAG="${ENVIRONMENT}-${VERSION}"

echo "Building artifacts for $ENVIRONMENT (tag: $IMAGE_TAG)..."

# Build Docker image
if [[ -f Dockerfile ]]; then
  if ! docker build -t "myapp:${IMAGE_TAG}" .; then
    echo "❌ Docker build failed"
    exit 1
  fi

  # Push to registry
  if ! docker push "myapp:${IMAGE_TAG}"; then
    echo "❌ Failed to push image to registry"
    exit 1
  fi

  echo "✅ Image built and pushed: myapp:${IMAGE_TAG}"
else
  # Non-Docker build (e.g., Go binary)
  if ! make build; then
    echo "❌ Build failed"
    exit 1
  fi

  echo "✅ Build artifacts created"
fi
```

### Expected Duration

- Docker build: 2-5 minutes (depends on cache)
- Registry push: 30-60s
- Total: ~3-6 minutes

---

## Phase 3: Validate Deployment Plan

Use parallel agents to validate the deployment plan and detect potential issues.

### Parallel Agent Integration

**Always uses parallel agents** (deployments are critical).

Execute:

```bash
~/.claude/scripts/parallel_agent.py --json --full-output --validate --timeout 600 \
  --cursor-model flash --claude-model sonnet \
  "Validate deployment plan for $ENVIRONMENT:
   - Version: $VERSION
   - Environment: $ENVIRONMENT
   - Changes: $(git log --oneline HEAD~5..HEAD)
   - Check for: breaking changes, migration requirements, config updates"
```

### Success Criteria

- [ ] Parallel agent consensus >= 80%
- [ ] No breaking changes detected
- [ ] Database migrations (if any) are backwards-compatible
- [ ] Environment config is complete

### On Failure

- If consensus 50-79%: Show disagreements to user, ask whether to proceed
- If consensus <50%: **BLOCK** - Do not deploy

### Implementation

```bash
echo "Validating deployment plan with parallel agents..."

# Get recent changes
CHANGES=$(git log --oneline HEAD~5..HEAD | head -5)

# Run parallel agent validation
VALIDATION_RESULT=$(~/.claude/scripts/parallel_agent.py --json --validate --timeout 600 \
  --cursor-model flash --claude-model sonnet \
  "Validate deployment plan for $ENVIRONMENT:
   Version: $VERSION
   Changes: $CHANGES

   Check for:
   - Breaking API changes
   - Database migration requirements
   - Configuration updates needed
   - Security concerns")

# Parse consensus score
CONSENSUS=$(echo "$VALIDATION_RESULT" | jq -r '.cross_verification.consensus_score')

if [[ $CONSENSUS -ge 80 ]]; then
  echo "✅ Deployment validated (consensus: ${CONSENSUS}%)"
elif [[ $CONSENSUS -ge 50 ]]; then
  echo "⚠️ Medium confidence (consensus: ${CONSENSUS}%)"

  # Show disagreements
  echo "$VALIDATION_RESULT" | jq -r '.agents | to_entries[] | "\(.key): \(.value.output)"'

  # Ask user
  # Use AskUserQuestion tool here with options:
  # - "Proceed with deployment"
  # - "Abort deployment"
else
  echo "❌ Low confidence (consensus: ${CONSENSUS}%)"
  echo "Deployment blocked - review findings and try again"
  exit 1
fi
```

### Expected Duration

- Parallel agents: 30-90s
- Total: ~1-2 minutes

---

## Phase 4: Deploy to Environment

Deploy to the target environment. **This phase is DESTRUCTIVE** - it modifies the running system.

### Success Criteria

- [ ] Deployment command succeeds
- [ ] Health check passes within 30s
- [ ] Service is reachable
- [ ] Previous version recorded for rollback

### On Failure

- **Automatic rollback** to previous version
- Alert team on Slack/email
- Do NOT retry automatically (human review required)

### Implementation

```bash
echo "Deploying to $ENVIRONMENT..."

# Record current version for rollback
PREVIOUS_VERSION=$(kubectl get deployment myapp -n $ENVIRONMENT -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "none")

echo "Previous version: $PREVIOUS_VERSION"
echo "New version: myapp:${IMAGE_TAG}"

# Deploy based on infrastructure
if command -v kubectl &>/dev/null; then
  # Kubernetes deployment
  if ! kubectl set image deployment/myapp myapp="myapp:${IMAGE_TAG}" -n $ENVIRONMENT; then
    echo "❌ Deployment failed"

    # Rollback
    if [[ "$PREVIOUS_VERSION" != "none" ]]; then
      echo "Rolling back to $PREVIOUS_VERSION..."
      kubectl set image deployment/myapp myapp="$PREVIOUS_VERSION" -n $ENVIRONMENT
    fi

    exit 1
  fi

  # Wait for rollout
  if ! kubectl rollout status deployment/myapp -n $ENVIRONMENT --timeout=60s; then
    echo "❌ Rollout failed"

    # Rollback
    if [[ "$PREVIOUS_VERSION" != "none" ]]; then
      echo "Rolling back to $PREVIOUS_VERSION..."
      kubectl rollout undo deployment/myapp -n $ENVIRONMENT
    fi

    exit 1
  fi

elif [[ -f docker-compose.yml ]]; then
  # Docker Compose deployment
  export IMAGE_TAG

  if ! docker compose up -d; then
    echo "❌ Docker Compose deployment failed"

    # Rollback (restart with previous compose state)
    docker compose down
    exit 1
  fi
else
  echo "❌ No deployment method found (kubectl or docker-compose)"
  exit 1
fi

echo "✅ Deployment successful"

# Wait for service to be ready
echo "Waiting for service health check..."
for i in {1..30}; do
  if curl -sf http://localhost:8080/health >/dev/null 2>&1; then
    echo "✅ Service is healthy"
    break
  fi

  if [[ $i -eq 30 ]]; then
    echo "⚠️ Service health check timeout (but deployment succeeded)"
  fi

  sleep 1
done
```

### Expected Duration

- Deployment: 10-30s
- Health check: 10-30s
- Total: ~30-60s

---

## Phase 5: Verify Deployment

Run smoke tests and verify the deployment is working correctly.

### Success Criteria

- [ ] Smoke tests pass
- [ ] Key endpoints respond correctly
- [ ] Database connectivity confirmed
- [ ] No error spike in logs

### On Failure

- Do NOT rollback automatically (deployment succeeded)
- Alert team immediately
- Log findings for investigation
- Mark deployment as "succeeded with warnings"

### Implementation

```bash
echo "Running post-deployment verification..."

# Smoke tests
if [[ -f tests/smoke.sh ]]; then
  if ! bash tests/smoke.sh; then
    echo "⚠️ Smoke tests failed (but deployment is live)"
    # Don't exit - just warn
  else
    echo "✅ Smoke tests passed"
  fi
fi

# Check key endpoints
ENDPOINTS=(
  "http://localhost:8080/health"
  "http://localhost:8080/api/version"
)

failed_endpoints=0
for endpoint in "${ENDPOINTS[@]}"; do
  if ! curl -sf "$endpoint" >/dev/null 2>&1; then
    echo "⚠️ Endpoint failed: $endpoint"
    ((failed_endpoints++))
  fi
done

if [[ $failed_endpoints -eq 0 ]]; then
  echo "✅ All endpoints responding"
else
  echo "⚠️ $failed_endpoints endpoints failed"
fi

# Check logs for errors (last 5 minutes)
if command -v kubectl &>/dev/null; then
  ERROR_COUNT=$(kubectl logs -n $ENVIRONMENT deployment/myapp --since=5m | grep -i "error\|exception\|panic" | wc -l)

  if [[ $ERROR_COUNT -gt 10 ]]; then
    echo "⚠️ High error rate in logs ($ERROR_COUNT errors in 5min)"
  else
    echo "✅ Error rate normal ($ERROR_COUNT errors in 5min)"
  fi
fi

echo "✅ Deployment verification complete"
```

### Expected Duration

- Smoke tests: 10-30s
- Endpoint checks: 5-10s
- Log analysis: 5-10s
- Total: ~30-60s

---

## Summary Output

After all phases complete (or fail), provide a summary:

```markdown
## Deployment Pipeline Summary

| Phase | Status | Duration | Notes |
|-------|--------|----------|-------|
| 1. Run Tests | ✅ pass | 2m 15s | Coverage: 87% |
| 2. Build Artifacts | ✅ pass | 3m 42s | Image: myapp:staging-abc123 |
| 3. Validate Plan | ✅ pass | 1m 8s | Consensus: 92% |
| 4. Deploy | ✅ pass | 45s | Rollout complete |
| 5. Verify | ⚠️ warn | 32s | 1 endpoint slow to respond |

**Overall**: SUCCESS (with warnings)
**Environment**: staging
**Version**: abc123
**Total Duration**: 8m 22s
**Deployed At**: 2026-02-04 18:45:23 UTC

**Post-Deployment Notes**:
- Endpoint /api/reports slow (2.1s response)
- Recommend monitoring for 30 minutes
- Rollback command: kubectl rollout undo deployment/myapp -n staging
```

---

## Error Recovery

### Network Timeout During Build

```bash
# Phase 2 can retry once
if ! docker push "myapp:${IMAGE_TAG}"; then
  echo "Push failed, retrying in 5s..."
  sleep 5

  if ! docker push "myapp:${IMAGE_TAG}"; then
    echo "❌ Push failed after retry"
    exit 1
  fi
fi
```

### Low Consensus in Validation

```bash
# Phase 3 asks user
if [[ $CONSENSUS -lt 80 && $CONSENSUS -ge 50 ]]; then
  # Use AskUserQuestion tool
  # Present findings and ask: Proceed or Abort?
fi
```

### Deployment Rollback

```bash
# Phase 4 automatic rollback
if ! kubectl rollout status deployment/myapp -n $ENVIRONMENT --timeout=60s; then
  echo "Deployment failed, rolling back..."
  kubectl rollout undo deployment/myapp -n $ENVIRONMENT
  kubectl rollout status deployment/myapp -n $ENVIRONMENT
  echo "✅ Rollback complete"
  exit 1
fi
```

---

## Customization

### For Different Deployment Targets

**AWS ECS**:

```bash
# Replace Phase 4 implementation
aws ecs update-service --cluster $CLUSTER --service myapp --force-new-deployment
```

**Heroku**:

```bash
# Replace Phase 4 implementation
git push heroku main
```

**VM/SSH**:

```bash
# Replace Phase 4 implementation
scp ./binary $HOST:/opt/myapp/
ssh $HOST 'sudo systemctl restart myapp'
```

### For Different Test Frameworks

**Go**:

```bash
# Phase 1
go test ./... -cover -coverprofile=coverage.out
go tool cover -func=coverage.out | grep total | awk '{if ($3+0 < 80) exit 1}'
```

**JavaScript**:

```bash
# Phase 1
npm test -- --coverage --coverageThreshold='{"global":{"lines":80}}'
```

### Adding Database Migrations

Add as Phase 2.5 (between Build and Validate):

```markdown
## Phase 2.5: Run Database Migrations

**Success Criteria**:
- [ ] Migrations run successfully
- [ ] No data loss
- [ ] Backwards compatible (old code still works)

**Implementation**:
```bash
# Django
python manage.py migrate --no-input

# Alembic (Python)
alembic upgrade head

# Go migrate
migrate -path ./migrations -database "$DATABASE_URL" up
```

```

---

## Related Patterns

- **Command State Machine Pattern**: `templates/patterns/command-state-machine.md`
- **Parallel Agent Integration**: Used in Phase 3 for validation
- **Error Recovery**: Demonstrated in Phase 4 rollback

---

## Integration with GitHub Actions

This command can be triggered by CI/CD:

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Staging
        run: |
          claude run /full-deployment-pipeline staging
```

---

## Monitoring & Alerting

After Phase 5, optionally send alerts:

```bash
# Slack notification
curl -X POST $SLACK_WEBHOOK -d '{
  "text": "Deployment to $ENVIRONMENT complete: $VERSION"
}'

# Email notification
echo "Deployment summary" | mail -s "Deploy: $VERSION to $ENVIRONMENT" team@example.com
```

---

## Testing This Command

### Simulate Success

```bash
# All phases should pass
/full-deployment-pipeline staging
```

### Simulate Test Failure

```bash
# Force tests to fail
export PYTEST_ADDOPTS="--maxfail=1"
pytest tests/unit/test_broken.py  # Make this fail
/full-deployment-pipeline staging
# Should stop at Phase 1
```

### Simulate Low Consensus

```bash
# Modify code to trigger disagreement between agents
# Add ambiguous security pattern
/full-deployment-pipeline staging
# Should pause at Phase 3 for user input
```

### Simulate Deployment Failure

```bash
# Simulate kubectl failure
alias kubectl="exit 1"
/full-deployment-pipeline staging
# Should rollback automatically
```

---

## See Also

- [Command State Machine Pattern](../patterns/command-state-machine.md)
- [GitHub Issue Process Command](../github-workflow/issue-process.md)
- [Migration Check Command](./migration-check.md)
