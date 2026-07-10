# Data Model: Critic-Driven Development Loop (CDDL)

**Feature**: `482-critic-dev-loop` | **Date**: 2026-07-10

Entities are persisted as JSON inside the run directory
(`${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/state.json`
plus per-iteration files) — see [contracts/cli-interface.md](contracts/cli-interface.md)
for the on-disk layout.

## FeatureContext

Normalized input to a run (spec FR-001, FR-002).

| Field | Type | Notes |
|---|---|---|
| `layout_type` | enum `speckit \| superpowers \| explicit` | from discovery seam; `explicit` when `--spec/--plan` provided |
| `spec_path` | string (abs path) | required; run refuses without it (pre-flight) |
| `plan_path` | string \| null | optional; absence recorded and disclosed to critics |
| `spec_content` / `plan_content` | string | snapshotted at run start (immutable for the run) |
| `clarifications` | list[ClarificationRound] | grows only during phase 1 |

Validation: `spec_content` non-empty; `tasks` role, if discovered, is ignored (never
required, never reported missing — FR-002).

## RoleDefinition

One loop participant, loaded from `configs/claude/prompts/cddl/<file>.md` (deployed:
`~/.claude/prompts/cddl/`) — spec FR-013.

| Field | Type | Notes |
|---|---|---|
| `role_key` | enum `implementer \| qa_critic \| arch_critic` | fixed set, v1 |
| `name` | string | frontmatter; must equal file stem |
| `description` | string | frontmatter |
| `model` | string alias (e.g. `sonnet`) | frontmatter; passed to `--model` |
| `prompt_body` | string | markdown body after frontmatter = system prompt |
| `source_path` | string | for error messages |

Validation (pre-flight, before any model call — FR-013): file exists, frontmatter
parses, `name`/`description`/`model` present and non-empty, body non-empty. Any
failure → exit 6 with the offending path.

## Run

One invocation lifecycle over one FeatureContext (spec Key Entities: Run).

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | `YYYYMMDDTHHMMSSZ-<4char>` UTC |
| `repo_root` | string | realpath of target repo |
| `branch` | string | must differ from default branch (FR-011) |
| `created_at` / `finished_at` | ISO-8601 UTC | |
| `config` | RunConfig | resolved ceilings/timeouts/flags snapshot |
| `phase` | enum `preflight \| clarify \| implement \| done` | |
| `status` | enum below | |
| `clarification_rounds` | list[ClarificationRound] | ≤ `config.max_rounds` |
| `iterations` | list[IterationRef] | ≤ `config.max_iterations` |
| `written_paths` | list[string] | repo-relative; every path the loop wrote across iterations |
| `staged_paths` | list[string] | exactly the final approved candidate's paths — the staging set (D9); earlier-iteration leftovers stay unstaged and are reported |
| `report_path` | string | `report.md` in run dir |

`status` enum and exit-code mapping (contracts/cli-interface.md):
`running` · `questions_pending`(3) · `success`(0) · `gate_failure`(4) ·
`ceiling_failure`(5) · `preflight_failure`(6) · `aborted`(7).

### State transitions

```text
(start) → preflight ─fail→ preflight_failure(6)
   preflight ─ok→ clarify
   clarify ─open questions & rounds<max→ questions_pending(3)  [re-entry: answer]
   clarify ─both critics complete→ implement
   clarify ─rounds exhausted w/ open questions→ gate_failure(4)
   implement ─both critics approve iteration N→ success(0) [stage written_paths]
   implement ─iterations exhausted→ ceiling_failure(5) [leave unstaged]
   any phase ─unrecoverable critic / run deadline / signal→ aborted(7) [leave unstaged]
```

Invariants: `success` requires both phase-2 verdicts of the final iteration to be
`approve` (FR-005) AND verification passed for that iteration (FR-009); staging
happens only in the `implement → success` transition (FR-011); every transition
appends an audit event (FR-010, fail-open).

## RunConfig

| Field | Default | Source |
|---|---|---|
| `max_rounds` | 3 | `--max-rounds` / `CDDL_MAX_ROUNDS` (FR-004) |
| `max_iterations` | 10 | `--max-iterations` / `CDDL_MAX_ITERATIONS` (FR-008) |
| `invoke_timeout_s` | 600 | `--invoke-timeout` / `CDDL_INVOKE_TIMEOUT` (FR-008) |
| `run_timeout_s` | 3600 | `--run-timeout` / `CDDL_RUN_TIMEOUT` (FR-008) |
| `verify_cmd` | auto-detect | `--verify-cmd` (FR-009, D8) |
| `allow_dirty` | false | `--allow-dirty` (FR-011) |
| `cli` | `claude` | `CDDL_CLI` (FR-012, D4) |

## ClarificationRound

One phase-1 round (spec Key Entities: Clarification Exchange; FR-003/FR-004).

| Field | Type | Notes |
|---|---|---|
| `round` | int (1-based) | |
| `critic_outputs` | map role_key → {raw_path, verdict} | both critics, independent |
| `questions` | list[{role_key, text}] | empty iff both signaled `complete` |
| `answers_text` | string \| null | operator answers (appended to context, FR-003) |

## Iteration

One phase-2 cycle (spec Key Entities: Iteration), persisted under
`iterations/<n>/` (FR-010).

| Field | Type | Notes |
|---|---|---|
| `n` | int (1-based) | |
| `candidate` | CandidateChange \| null | null when parse/confinement rejected pre-write |
| `verification` | {ran: bool, cmds: list, passed: bool, output_path} | `ran=false` disclosed (FR-009) |
| `verdicts` | map role_key → Verdict | critics run only when verification passed |
| `deficiencies` | list[Deficiency] | fed into iteration n+1 context (FR-007) |
| `stalled` | bool | candidate byte-identical to previous → flagged (edge case) |
| `started_at` / `ended_at` | ISO-8601 | |

## Verdict

A single critic's structured judgment (spec Key Entities: Verdict; FR-006).
Parsed per [contracts/verdict-format.md](contracts/verdict-format.md).

| Field | Type | Notes |
|---|---|---|
| `role` | string | must equal invoked role_key else non-approval |
| `decision` | enum `approve \| reject \| questions \| complete` | phase-appropriate subset enforced |
| `findings` | list[{title, detail, severity?}] | required non-empty for `reject`/`questions` |
| `parsed_ok` | bool | false ⇒ treated as non-approval; one retry then abort |
| `raw_path` | string | full raw output persisted (FR-010) |

## Deficiency

| Field | Type | Notes |
|---|---|---|
| `source` | enum `qa_critic \| arch_critic \| verification \| confinement` | FR-007, FR-009, FR-017 |
| `iteration` | int | attribution |
| `text` | string | actionable finding fed to next iteration |

## CandidateChange

Implementer output (spec Key Entities: candidate; FR-017), grammar in
[contracts/candidate-format.md](contracts/candidate-format.md).

| Field | Type | Notes |
|---|---|---|
| `files` | list[{path, content}] | path repo-relative; full-file content (D10) |
| `notes` | string \| null | implementer's non-code remarks (ignored by apply) |

Validation (all-or-nothing, pre-write): every `path` relative, no `..` segment, no
absolute path, parent-dir realpath contained in repo_root realpath (symlink escape
check). Any violation ⇒ candidate rejected whole, `confinement` deficiency recorded,
zero writes (FR-017).
