# Phase 1 Data Model — Autonomous PR Lifecycle & Merge Loop

No database; these are in-memory/JSON shapes passed between the loop and its helpers, plus the
audit record persisted via `audit_log.sh`.

## Managed-PR state machine

```text
            ┌─────────────┐
   open ───▶│ MONITORING  │  poll review-state + CI (self-paced, ≤ceiling)
            └─────┬───────┘
                  │ actionable comments OR CI failure
                  ▼
            ┌─────────────┐  /address-pr-comments, /verify, /pr-review
            │ ADDRESSING  │◀──┐  (one revision cycle)
            └─────┬───────┘   │ not clear AND revisions < max
                  │ clear     │
                  ▼           │
            ┌─────────────┐   │
            │  VERIFIED   │───┘  re-check after push
            └─────┬───────┘
       all clear conditions hold (CI green, no human block,
       /pr-review=merge, /verify pass, gate Tier-1 pass, consensus≥0.80)
                  │
        ┌─────────┼───────────────────────────┐
        ▼         ▼                           ▼
   ┌────────┐  ┌────────────┐          ┌──────────────┐
   │ MERGED │  │ NEEDS-HUMAN│          │   HALTED     │
   └───┬────┘  └────────────┘          └──────────────┘
       │  (post-merge main CI)   revisions exhausted,    main CI red after a
       ▼                         conflict, no admin,     merge → stop ALL further
  main green → continue          human block, consensus  merges until human clears
  main RED  → HALTED             0.50–0.79
```

**Terminal-for-this-PR states**: `MERGED`, `NEEDS-HUMAN`. **Loop-terminal**: `HALTED` (stops
the whole loop, not just this PR).

## Entities

### Work item
A unit the loop processes: a new issue to develop **or** a managed PR to monitor/merge.
- `kind`: `issue` | `pr`
- `ref`: issue/PR number
- `state`: develop | one of the managed-PR states above

### Managed PR
- `number`, `author_login`, `head_ref`, `base` (= main)
- `state`: MONITORING | ADDRESSING | VERIFIED | MERGED | NEEDS-HUMAN | HALTED
- `revisions_used`: int (0…max, default max 3)
- derived signals (recomputed each pass, never cached across runs):
  - `checks`: PASS | PENDING | FAIL | NO_CHECKS (R3)
  - `review_block`: bool — human CHANGES_REQUESTED or unresolved human thread (R2)
  - `pr_review_disposition`: merge | needs-rebase | close | keep
  - `verify`: pass | fail-blocking (test/security) | warn (lint)
  - `gate_tier1`: pass | fail (#360 verification gate)
  - `consensus`: float 0–1
  - `mergeable`: MERGEABLE | CONFLICTING | UNKNOWN; `merge_state`: CLEAN|BEHIND|DIRTY|… (R4)
  - `hold`: bool — `hold` label present

### Clear conditions (all must hold to MERGE — FR-007, Principle II)
`checks==PASS` **and** `review_block==false` **and** `pr_review_disposition==merge` **and**
`verify==pass` **and** `gate_tier1==pass` **and** `consensus>=0.80` **and** `hold==false`
**and** `mergeable==MERGEABLE && merge_state ∈ {CLEAN,HAS_HOOKS}`.
> `NO_CHECKS` is **not** PASS — it routes to NEEDS-HUMAN (don't auto-merge un-CI'd code).

### Revision cycle
One `/address-pr-comments` + `/verify` + `/pr-review` pass against a PR; increments
`revisions_used`. Budget exhausted (`>= max`) → NEEDS-HUMAN.

### Empty-run counter (FR-018, FR-018a)
- `consecutive_empty`: int; loop stops at `>= 5`.
- A run is **empty** only when zero issues to develop **and** zero managed PRs in any active
  state (MONITORING/ADDRESSING/VERIFIED, or PENDING checks). Any work or in-flight PR → reset/no-increment.

### Automation-author allowlist (FR-013)
Config-driven set of bot/automation logins (auto-dev account + Forge/Palette/Jules/Bolt/Copilot).
`author_login ∉ allowlist` → the PR is human-authored → skipped (not counted as work).

### Audit record (extends existing `auto-issue-dev` record — FR-021)
`{ ts, pr, action: monitor|address|merge|hand-human|halt, outcome, revisions_used,
   consensus, gate_tier1, checks, reason }` — redacted, fail-open (write failure never blocks).

## Labels (config: `labels.yml`)
- **New**: `ready-to-merge` (verified but couldn't auto-merge — for a human), `loop-active`
  (transient concurrency lock), `hold` (human "do not auto-merge").
- **Reused**: `needs-human`, `blocked-dependency`, `auto-dev`.
