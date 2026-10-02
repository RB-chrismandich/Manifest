# Contract — `merge_decision.sh` (pure deterministic core)

The safety-critical decision logic, isolated from all I/O so it is fully bats-testable offline
(mirrors #360 `verification_gate.sh decide`). No network, no `gh`, no filesystem writes.

## `merge_decision.sh decide <signals-json>`

**Input** (stdin or `$1`): the recomputed signals for one managed PR.
```json
{
  "checks": "PASS|PENDING|FAIL|NO_CHECKS",
  "review_block": false,
  "pr_review_disposition": "merge|needs-rebase|close|keep",
  "verify": "pass|fail-blocking|warn",
  "gate_tier1": "pass|fail",
  "consensus": 0.86,
  "mergeable": "MERGEABLE|CONFLICTING|UNKNOWN",
  "merge_state": "CLEAN|BEHIND|DIRTY|BLOCKED|UNSTABLE|DRAFT|HAS_HOOKS|UNKNOWN",
  "hold": false,
  "revisions_used": 1,
  "max_revisions": 3,
  "reviewer_error": false,
  "main_ci": "green|red|pending|n/a"
}
```

**Output** (stdout JSON): `{ "action": "...", "reason": "...", "label": "..."|null }`

**Decision table** (first match wins — fail-closed ordering):

| Condition | action | label |
|-----------|--------|-------|
| `main_ci == "red"` | `halt` | — |
| `reviewer_error` or `gate_tier1=="fail"` (gate can't run / Tier-1 fail) | `hand-human` | `needs-human` |
| `hold` or `review_block` (human block) | `hand-human` | `needs-human` |
| `mergeable=="CONFLICTING"` or `merge_state=="DIRTY"` | `hand-human` | `needs-human` |
| `merge_state=="BEHIND"` (clean, just stale) | `update-branch` | — |
| `checks=="FAIL"` or `verify=="fail-blocking"` and `revisions_used < max` | `revise` | — |
| `checks=="PENDING"` or `mergeable=="UNKNOWN"` or `merge_state ∈ {UNSTABLE,UNKNOWN}` | `wait` | — |
| not clear and `revisions_used >= max` | `hand-human` | `needs-human` |
| `checks=="NO_CHECKS"` | `hand-human` | `needs-human` |
| all clear conditions hold **and** `consensus >= 0.80` | `merge` | — |
| all clear **but** `0.50 <= consensus < 0.80` | `hand-human` | `ready-to-merge` |
| all clear **but** `consensus < 0.50` | `hand-human` | `needs-human` |

**Exit codes**: `0` always (the decision is the payload; the caller acts on `action`). Malformed
input → `action:"hand-human", reason:"unparseable signals"` (fail closed), exit `0`.

**Invariants the bats suite MUST cover** (one test per row + these):
- `main_ci==red` overrides everything (halt wins even if all else is clear).
- A `gate_tier1==fail` is never `merge`, regardless of consensus.
- `NO_CHECKS` never yields `merge`.
- `consensus` only ever downgrades `merge`→`hand-human`; it never upgrades a blocked state.
- No input combination yields `merge` while any hard block (review_block, hold, conflict,
  gate fail, failing/pending/absent checks) is set — this is SC-002 as a unit invariant.
