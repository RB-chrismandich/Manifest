# Quickstart: Autonomous Issue Implementation Orchestrator

**Date**: 2026-06-14 | **Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This quickstart shows how the orchestrator is configured, run, and validated once implemented. Paths are repo-relative; the daemon is deployed to `~/.claude/` via `bootstrap.sh`.

## Prerequisites

- `gh` or `glab` authenticated for the target repository.
- `speckit`, `agy`, and the Claude/Gemini CLI backends available (the daemon reuses `parallel_agent.py` backend selection).
- Python 3.11+, and the repo deployed via `./bootstrap.sh`.

## 1. Configure

```bash
# Orchestrator config (new) — phase order, 2-attempt cap, hourly resume poll,
# consensus threshold source, redaction patterns, audit path.
$EDITOR configs/claude/config/orchestrator.yml

# Provision the kill-switch label across the tracker.
configs/claude/scripts/label_sync.sh            # adds `no-automation` from labels.yml
```

## 2. Run the daemon

```bash
# Start the long-running orchestrator (drives ONE issue at a time to a clean PR).
configs/claude/scripts/orchestrator/daemon.py --repo <owner/repo>

# Dry-run a single phase against a recorded payload (no side effects):
configs/claude/scripts/orchestrator/daemon.py --phase 1 --payload fixtures/backlog.json --dry-run
```

## 3. Observe & control

```bash
# Tail the durable, redacted audit trail (FR-029/FR-038).
tail -f ~/.claude/state/orchestrator/audit-*.jsonl

# Emergency stop a specific issue mid-pipeline: apply the kill-switch label.
gh issue edit <n> --add-label no-automation     # halts before the next phase advance (FR-037)
```

## 4. Acceptance walkthrough (maps to spec user stories)

| Step | Action | Expected (spec ref) |
|------|--------|---------------------|
| US1 | Feed a backlog where a low-severity issue blocks three others | That issue is ranked #1; justification states the unblock-vs-severity trade-off (FR-009) |
| US2a | Run with a dirty pre-impl analysis (one warning) | Implementation blocked, required-fix emitted (FR-017) |
| US2b | Post-implementation, leave one task acceptance criterion unmet | Verification gate blocks PR-open as a Tier 1 finding, even with tests green (FR-032) |
| US2c | Post-implementation with only Tier 2 findings | PR opens; Tier 2 findings attached as advisory annotations (FR-031) |
| US3 | Provide an `agy` recommendation that conflicts with a repo pattern | Repo-consistent option chosen; conflict logged with rejected alternative (FR-012) |
| US4 | Provide a CI failure + review comments | Root-cause modifications + PR reply ending in ✅/🛠️ (FR-020–FR-022) |
| US5 | Submit malformed input / embedded "ignore your rules" | `blocked` + escalation; directive ignored and noted (FR-005/FR-023) |
| Kill-switch | Apply `no-automation` to the active issue mid-run | Issue halts, reported as held; never implemented (FR-037/SC-015) |
| Resource pause | Exhaust agent tokens at a gate | Phase pauses (transient), resumes hourly, no attempt increment, no escalation (FR-035/SC-014) |

## 5. Validate

```bash
pytest tests/python/test_orchestrator_*.py     # determinism, envelope validation, consensus, retry/pause, redaction, audit
bats tests/bats/orchestrator_*.bats            # daemon --help, label sync, idempotent install
shellcheck configs/claude/scripts/orchestrator/*.sh 2>/dev/null || true
yamllint configs/claude/config/orchestrator.yml
python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('specs/004-autonomous-issue-orchestrator/contracts/*.json')]"
```

**Success signals**: 100% envelope-conformant responses (SC-001), deterministic re-runs (SC-002), 0 PRs opened with an unresolved Tier 1 finding (SC-011), ≥90% first-run CI pass (SC-012), 0 unredacted secrets in the audit (SC-016), median ≤30 min active processing (SC-017).
