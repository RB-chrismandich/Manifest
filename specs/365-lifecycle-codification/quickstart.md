# Quickstart: Codified State-Gated Development Lifecycle

**Feature**: 365-lifecycle-codification | End-to-end usage once implemented. Validates US1–US5.

## Prerequisites
- `./bootstrap.sh` has deployed the updated `spec_review.sh` (with `--mode`) and `lifecycle.sh` to `~/.claude/scripts/`.
- Smoke orchestrator present (`~/.claude/scripts/smoke_test.py`); Atlassian MCP wired in `settings.local.json` (for Jira).
- Constitution at v1.1.0 (Principle VI + Development Lifecycle section).

## 1. Start a track from a ticket (US1, US4)
```bash
# Any provider — entry point is a URL or issue key
lifecycle.sh init PROJ-123                         # Jira (via MCP)
lifecycle.sh init org/repo#42                      # GitHub
lifecycle.sh status PROJ-123 --json               # → current_phase=specify, tier classified
```
Expect: a track file under `$MANIFEST_STATE_ROOT/lifecycle/state/jira__PROJ-123.json`; an unrecognized entry point errors with **no** track created.

## 2. Drive the phases — skipping is refused (US1)
```bash
# Try to jump ahead → hard refuse for agents, advisory for humans
echo '{"actor_mode":"agent","current_phase":"clarify","requested_phase":"implement","completed_phases":["specify"]}' \
  | lifecycle.sh decide -
# → {"action":"refuse","missing_prereq":"spec_review_product","reason":"..."}
```
Run phases in order; each `advance` validates the prior phase's exit criteria:
```bash
/speckit-specify … && lifecycle.sh advance PROJ-123        # → clarify
/speckit-clarify … && lifecycle.sh advance PROJ-123        # → spec_review_product
spec_review.sh --mode product --format json … ; lifecycle.sh advance PROJ-123   # APPROVED→advance
/speckit-plan … && lifecycle.sh advance PROJ-123
/speckit-tasks … && /speckit-taskstoissues … && lifecycle.sh advance PROJ-123   # provisions 4-tier hierarchy
/speckit-analyze … ; lifecycle.sh advance PROJ-123
spec_review.sh --mode technical --format json … ; lifecycle.sh advance PROJ-123
```

## 3. Implement with coverage, then Verify gate (US2)
```bash
# During Implement: author a smoke test per user-facing workflow
smoke_test.py append --from workflow.json           # tier: Lite for critical path
# Implement EXIT: coverage reconciliation
smoke_test.py list --app <unit> --json              # every shipped workflow id must be present (or exempt)
lifecycle.sh advance PROJ-123                        # refuses if coverage MISSING
# Verify gate
smoke_test.py run --app <unit> --tier Lite --junit verify-report.xml
lifecycle.sh advance PROJ-123                        # exit 0 → done; exit 1/2 → refuse (2=EMPTY=missing coverage)
```
Expect: a unit cannot reach `done` with a non-exempt user-facing workflow lacking a passing Lite test (SC-003).

## 4. Hierarchy across providers (US3)
```bash
lifecycle.sh status PROJ-123 --json | jq .hierarchy_ref   # Initiative→Epic→Task→Sub-Task ids
```
A target lacking a tier (e.g. GitHub Initiative) → configuration error naming the tier (not a silent mismap). Partial provisioning failure → node `FAILED_PROVISION`, flagged for reconciliation, no orphaned local state.

## 5. Governance & enforcement (US5)
```bash
# Constitution is the single source; phase/gate rules live there
grep -n "State-Gated Lifecycle" .specify/memory/constitution.md
# Autodev loop refuses to merge past a failing gate
# (auto loop calls lifecycle.sh gate; BLOCKED/FAIL → halt + needs-human, never merges)
```
Tracker-originated status change (human moves the Jira ticket to Done) is reconciled on the next loop tick without a sync loop (SC-010).

## Acceptance smoke (maps to success criteria)
| Check | Expect | SC |
|---|---|---|
| Agent skip attempt | refused, prerequisite named | SC-001/002 |
| Human skip attempt | warned, override logged | SC-002 |
| Reach done w/o coverage | blocked | SC-003 |
| Same flow on GH/GL/Linear/Jira | identical phases | SC-004 |
| Missing tier | config error | SC-005 |
| Partial provisioning | no orphaned local state | SC-006 |
| `status` query | phase + completed + outstanding gates | SC-007 |
| Change phase rule once | constitution only; docs consistent | SC-008 |
| Logs/state | no secrets | SC-009 |
| Tracker-side status change | reconciled, no loop | SC-010 |
| Failing gate under loop | halt + needs-human, no merge | SC-011 |
