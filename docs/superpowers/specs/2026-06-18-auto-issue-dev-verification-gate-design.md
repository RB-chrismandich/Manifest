# auto-issue-dev: post-implementation verification gate — design

**Date**: 2026-06-18
**Issue**: [#360](https://github.com/ReefBytes-Owner/Manifest/issues/360)
**Source**: harvested from #346 (specs/004 — orchestrator, abandoned); this is the
keystone "verification gate" idea re-implemented for the lean `auto-issue-dev` skill.
**Status**: Design — approved for planning

---

## Goal

Before `auto-issue-dev` opens a **real** PR, run a verification gate that reuses the
**existing** `parallel_agent.py` consensus engine and the repo's tiered model
(`validation_criteria.yml`). **Tier 1** findings (security, error handling, breaking
changes, acceptance-criteria coverage) **block** real-PR-open and route the work to a
draft for a human. **Tier 2** (bugs, perf, maintainability, coverage) and the
**consensus score** are advisory — annotated on the PR, never blocking.

## Non-goals

- No change to `parallel_agent.py` / the `agents/` package or its consensus
  (`ValidationEngine`) machinery. The gate is a **consumer**, not a modification.
- No new daemon, no orchestrator package (that was #346/specs/004, abandoned).
- No live-LLM end-to-end test (matches #346's deferred T052; the live review path is
  exercised only through an injectable seam in tests).

## Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Gate placement vs `/verify` | **Wrap** — gate runs as a new step *after* `/verify`, only if `/verify` did not already block. Both the deterministic (lint/test/security) and semantic (consensus) signals are preserved. |
| 2 | Gate policy | **Tier-1-only blocks; consensus advisory.** A Tier 1 failure forces a draft + `needs-human`. The consensus score is always annotated, never blocks. |
| 3 | Infrastructure failure (reviewer cannot run at all) | **Fail-closed → draft + `needs-human`.** A reviewer outage must never let un-reviewed code reach a real (mergeable) PR. |
| 4 | Spec home | Superpowers design doc (this file) + implementation plan in `docs/superpowers/plans/`. |

> **Consensus is advisory, by construction.** The shared `ValidationEngine` treats
> `cross_verification` (consensus ≥ 0.80) as a *Tier 1* check, so reused verbatim it
> would block at <80% consensus. To honor decision #2, the `auto-issue-dev`
> command-override lists Tier 1 checks **without** `cross_verification`. The consensus
> score is still computed and reported — it just does not gate.

---

## Architecture

A new **step 5.5** in the `auto-issue-dev` skill, between `/verify` (step 5) and the
Outcome step (step 6). The gate is split into two cleanly separated halves so the
non-deterministic part is isolated from the part that carries the safety logic:

```text
Step 4: develop test-first
Step 5: /verify                         ── deterministic; blocks on test/security fail
Step 5.5: VERIFICATION GATE (new)
          ├─ review  (non-deterministic) → parallel_agent.py --json --validate --review
          └─ decide  (deterministic)     → verdict JSON → {action, label, annotation}
Step 6:  Outcome
          ├─ Tier 1 PASS → real PR  (consensus % + Tier 2 concerns annotated)
          └─ Tier 1 FAIL │ infra-fail → draft PR + needs-human + mark-blocked
Step 7:  Audit  (existing; record extended with gate fields)
```

### Why a dedicated, testable helper

This change "reshapes the autonomy pipeline itself" (issue's trust-boundary note), so
the decision logic must be **defensible and unit-tested**, not buried in prose. The
repo strongly favors testable shell helpers (`auto_issue_dev.sh`, `audit_log.sh`) with
bats coverage. The gate therefore lives in a new script whose *deterministic core* is
fully testable offline.

---

## Components

### 1. New: `configs/claude/scripts/verification_gate.sh`

Repo script conventions apply: `err()` for all error/warning output, a `--help`
handler (≤15 lines, exit 0), `set -euo pipefail`.

**Subcommands:**

- **`review <issue-number>`** — orchestrates the non-deterministic review:
  1. Resolve the base branch and build the branch diff (`git diff <base>...HEAD`).
  2. Assemble a **review packet** temp file: the issue's acceptance criteria (from
     `auto_issue_dev.sh`/`git_ops.sh issue-view`) as a header, followed by the diff.
  3. **Redact** the packet through `audit_log.sh redact` before it leaves the process.
  4. Invoke the reviewer **behind an injectable seam** (env `VERIFICATION_GATE_REVIEW_CMD`,
     default `parallel_agent.py --json --validate --review <packet>`), piping the packet
     path/content per the `headless-llm-cli-seam` pattern (ARG_MAX-safe, offline-testable).
  5. Emit the gate JSON (`{tier1, tier2, verdict, consensus_score}`) on stdout.
  - On any reviewer failure (non-zero exit, empty/unparseable output, timeout) emit a
    sentinel gate JSON with `reviewer_error: true` so `decide` can fail-closed.

- **`decide <gate-json>`** — the **pure, deterministic core** (no I/O, no network).
  Maps the gate JSON to an action object:

  | Condition | `action` | `label` | annotation |
  |-----------|----------|---------|------------|
  | `reviewer_error: true` (infra fail) | `draft-needs-human` | `needs-human` | "verification gate could not run" |
  | `tier1.passed == false` (verdict `BLOCKED`) | `draft-needs-human` | `needs-human` | Tier 1 findings, listed |
  | `tier1.passed == true`, consensus ≥ high | `pr-open` | — | Tier 2 advisory note only |
  | `tier1.passed == true`, low ≤ consensus < high | `pr-open` | — | ⚠ disagreement note + Tier 2 concerns |

  Output: `{"action": "...", "label": "...", "annotation": "...", "reason": "..."}`.
  Thresholds (`high`/`low`) are read from `command_config.yml > consensus`
  (`high: 0.80`, `low: 0.50`); consensus only *changes the annotation*, never the action.

### 2. `validation_criteria.yml` — new `command_overrides.auto-issue-dev`

```yaml
auto-issue-dev:
  tier1_required: true
  tier1_checks:            # cross_verification deliberately OMITTED → consensus advisory
    - security
    - error_handling
    - breaking_changes
  tier2_required: true
  tier2_threshold: 0.60    # advisory only — never blocks the PR
  consensus_threshold: 0.80  # banding for annotation, not gating
  parallel_agents: true    # the gate itself is a parallel-agent review
```

**Acceptance-criteria coverage** is enforced as a Tier-1 blocking concern at the *gate*
level, not by adding a new check to the shared engine (which would change behavior for
every command). The review packet includes the issue's acceptance criteria, the review
prompt asks agents to flag any uncovered criterion as a critical finding, and `decide`
treats a coverage-gap finding the same as a Tier 1 failure → draft + `needs-human`.

### 3. `command_config.yml` — reconcile `tool_policies.auto-issue-dev`

Today: `parallel_agents: never`. That refers to the **develop** loop (the skill writes
code without spinning up cross-verification). The gate, however, *is* a deliberate,
bounded `parallel_agent.py` invocation. Reconcile by scoping the policy — e.g.
`parallel_agents: gate-only` with a comment — so the "never auto-wrap the dev output"
intent and the "the gate runs parallel agents" reality are both explicit and not in
apparent contradiction.

### 4. `auto-issue-dev/SKILL.md` — document step 5.5

- Insert step 5.5 between `/verify` and Outcome.
- Step 6 Outcome keys off the gate `action` (`pr-open` vs `draft-needs-human`).
- Extend the step-7 audit record with `gate_verdict`, `consensus`, `tier1_passed`.

---

## Data flow

```text
issue #N (acceptance criteria) ┐
git diff <base>...HEAD         ┘─▶ review packet (temp) ─▶ audit_log.sh redact
        ─▶ VERIFICATION_GATE_REVIEW_CMD (parallel_agent.py --json --validate --review)
        ─▶ gate JSON {tier1, tier2, verdict, consensus_score}
        ─▶ verification_gate.sh decide
        ─▶ {action, label, annotation, reason}
              ├─ pr-open          → git_ops.sh pr-create  (+ annotation in body)
              └─ draft-needs-human → git_ops.sh pr-create --draft
                                     + auto_issue_dev.sh mark-blocked <N> <reason>
        ─▶ audit_log.sh append  (record + gate_verdict, consensus, tier1_passed)
```

## Error handling

- **Fail-closed gate** (decision #3): any reviewer infrastructure failure → draft +
  `needs-human`. This is the deliberate opposite of the **fail-open** audit log
  (`audit_log.sh` never blocks a run) — the gate is a *safety control*, the audit log
  is *observability*.
- **Secret hygiene**: the diff/packet is redacted (`audit_log.sh redact`) before it
  reaches the reviewer, and the PR annotation is redacted before posting.
- **Large diffs / ARG_MAX**: the packet is a temp file; the reviewer seam consumes it
  by path/stdin, never as a giant argv string.
- **Temp-file lifecycle**: packet written under `mktemp`, removed via `trap` on exit.

## Testing

| Layer | Tool | Cases |
|-------|------|-------|
| `decide` (deterministic core) | bats | tier1-fail→draft; tier1-pass + high consensus→pr-open + advisory note; tier1-pass + mid consensus→pr-open + ⚠ disagreement note; `reviewer_error`→draft (infra fail); acceptance-criteria gap→draft |
| `review` orchestration | bats | `VERIFICATION_GATE_REVIEW_CMD` seam returns a fixture JSON; assert packet is redacted and well-formed; reviewer non-zero exit → `reviewer_error` sentinel |
| Script conventions | bats / shellcheck | `--help` exits 0 ≤15 lines; errors routed through `err()`; `shellcheck` clean |
| Config | `yamllint` + `python3 -c "yaml.safe_load(...)"` | edited `validation_criteria.yml` and `command_config.yml` parse |

No live-LLM test is required; the live review path is covered only via the seam.

## Risks & mitigations

- **Consensus semantics drift**: a future edit could re-add `cross_verification` to the
  override and silently turn the advisory consensus into a blocker. Mitigate with an
  inline comment in the YAML and a bats assertion that `auto-issue-dev` Tier 1 excludes
  `cross_verification`.
- **Gate cost**: each autonomous run now spends a parallel-agent review. Acceptable —
  it is the point — and bounded to one review per issue (the skill already does one
  issue per invocation).
- **False blocks**: an over-eager Tier 1 finding parks good work in a draft. This is the
  safe direction (human unblocks), and the audit record captures the verdict for review.

## Open items for the plan

- Exact base-branch resolution for the diff (reuse `git_ops.sh`/`git_platform.sh`).
- Precise shape of the review prompt that elicits acceptance-criteria-coverage findings
  in a form `decide` can parse.
- Whether `decide` parses the engine's `tier1.issues[]`/`tier2.concerns[]` arrays
  directly or a normalized projection.
