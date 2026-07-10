# Contract: `cddl_loop.py` CLI Interface

**Feature**: `482-critic-dev-loop` | Consumers: `/spec-implement-loop` skill, bats tests, smoke test

Entry point: `configs/claude/scripts/cddl_loop.py` (deployed `~/.claude/scripts/cddl_loop.py`).
Thin shim delegating to the `cddl` package; owns `--help` and the exit-code contract.

## Commands

### `cddl_loop.py start <target-path> [options]`

`<target-path>` may be a directory (feature dir / repo root) or an artifact
FILE (e.g. a superpowers design doc): a file target is the explicit spec by
FR-001 precedence and pairs its plan within its own layout tree.

Pre-flight (discovery, role validation, git checks, backend probe) then phase 1
round 1. If both critics signal `complete` with no questions, continues straight
into phase 2 within the same invocation.

| Option | Default | Meaning |
|---|---|---|
| `--spec <path>` / `--plan <path>` | — | explicit artifact override (wins over detection, FR-001) |
| `--verify-cmd '<cmd>'` | auto-detect | project verification gate (FR-009) |
| `--max-rounds N` | 3 | clarification round limit (FR-004) |
| `--max-iterations N` | 10 | phase-2 ceiling (FR-008) |
| `--invoke-timeout S` | 600 | per role invocation (FR-008) |
| `--run-timeout S` | 3600 | whole-run wall clock (FR-008) |
| `--allow-dirty` | off | override dirty-tree refusal (FR-011) |
| `--state-root <dir>` | `$MANIFEST_STATE_ROOT` or `~/.manifest` | run-dir root override |

### `cddl_loop.py answer --run <run-id> --answers-file <path>`

Re-entry after `questions_pending`: appends operator answers to the run context
(FR-003), executes the next clarification round; on gate pass proceeds into phase 2.
A missing answers file is a usage error (exit 2); an empty answers file or a run
not awaiting answers refuses with exit 6. Works from any cwd: the run is located
by run-id under the state root when the cwd is not the target repo (same for
`status --run`).

### `cddl_loop.py status [--run <run-id>]`

Prints the run's `state.json` summary (latest run for the current repo when
`--run` omitted). Read-only, exit 0 even for failed runs (exit 6 only if no run
exists).

### `cddl_loop.py --help` / `-h`

Usage + flags, ≤15 lines, exit 0, no config/state/dependency lookup beforehand
(repo `--help` convention, FR-016).

## Exit codes (stable contract)

| Code | Status | Meaning |
|---|---|---|
| 0 | `success` | dual approval; the final candidate's `staged_paths` staged |
| 2 | usage error | bad flags/args (argparse), nothing started |
| 3 | `questions_pending` | phase-1 questions written to `questions.md`; re-enter via `answer` |
| 4 | `gate_failure` | rounds exhausted with open questions; no code produced (FR-004) |
| 5 | `ceiling_failure` | iterations exhausted; candidate left applied, unstaged (FR-008, FR-011) |
| 6 | `preflight_failure` | unresolvable target / invalid role file / default branch / dirty tree / no backend (FR-016) |
| 7 | `aborted` | unrecoverable critic failure, run deadline, or signal (FR-006, FR-008) |

Every non-zero exit prints one actionable `cddl-loop: …` line to stderr via `err()`
(distinct message per end state — FR-016).

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `CDDL_CLI` | `claude` | injectable LLM CLI seam (D4; tests stub this) |
| `CDDL_MAX_ROUNDS` / `CDDL_MAX_ITERATIONS` | 3 / 10 | as flags |
| `CDDL_INVOKE_TIMEOUT` / `CDDL_RUN_TIMEOUT` | 600 / 3600 | seconds |
| `MANIFEST_STATE_ROOT` | `~/.manifest` | state root (shared repo convention) |
| `CDDL_AUDIT_FILE` | `~/.claude/cddl_audit.jsonl` | exported as `AUDIT_LOG_FILE` when invoking audit_log.sh (its generic file target; legacy `AUTO_ISSUE_DEV_AUDIT_FILE` still honored for issue-dev-auto) |

## Run directory layout (on-disk contract)

```text
${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/   (chmod 700)
├── state.json            # Run entity (data-model.md), atomically rewritten per transition
├── context.md            # snapshotted spec+plan+clarifications (grows in phase 1 only)
├── questions.md          # present iff status=questions_pending (per-critic sections)
├── answers-<round>.md    # operator answers as ingested
├── clarify/round-<n>-<role>.md   # raw phase-1 critic outputs (every attempt persisted)
├── iterations/<n>/
│   ├── backup/           # pre-images of files overwritten/deleted this iteration
│   ├── candidate.md      # raw implementer output
│   ├── files.json        # parsed CandidateChange (or rejection record)
│   ├── verify.log        # verification output (FR-009)
│   ├── qa_critic.md / arch_critic.md    # raw critic outputs
│   └── verdicts.json     # parsed Verdicts (FR-006)
└── report.md             # final report: status, per-critic outstanding deficiencies,
                          #   staged/unstaged disposition, discard instructions (FR-011)
```

Never auto-pruned (clarified: keep everything); each run dir is self-contained so
manual `rm -rf <run-id>` is safe.

## Concurrency

One active run per target repo: lock file under
`${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/locks/<repo-slug>.lock` (state-root
confined per FR-017 — not /tmp) with an mtime stale threshold equal to the run
wall-clock ceiling (pattern mirrors `loop_lock.sh`); a held lock → exit 6 with
the owning run-id in the message.
