# Design: Test → Backup → Deploy → Re-validate the 24h Change Set

**Date**: 2026-06-29
**Author**: Claude Code (brainstormed with user)
**Status**: Approved — pending written-spec review
**Topic**: End-to-end validation and live deploy of the last-24h Manifest changes

---

## 1. Goal & Scope

Validate every runnable change merged to `main` in the last 24 hours, deploy the
updates into the live `~/.claude` environment via `bootstrap.sh`, and confirm —
step by step, with real evidence — that everything works as expected.

**Diff range**: `4643b72..0722b88` (10 commits), comprising features 363–367 and
several bot opt PRs:

| Feature / PR | Surface |
|---|---|
| 365 | `lifecycle.sh` (803-line state-gated dev CLI), `lifecycle_providers.yml`, `/lifecycle` skill |
| 366 | coding-standards enforcement, `lint_on_edit_hook.sh`, no-bypass CI gate, `pyproject.toml` (new shared ruff/pytest config), `.editorconfig`, `.pre-commit-config.yaml` |
| 367 | sub-agent dispatch guidance (`command_config.yml` `tool_policies.subagents`, `subagent_policy.bats`, SKILL.md frontmatter across ~19 skills) |
| 364 | `graphify` skill + integration, bootstrap graphify gating, `services.yml` |
| 363 | smoke-test orchestrator, `smoke-orchestrator` skill |
| #434/#436/#437/#438/#435 | rsync-resilient skill deploy, semantic-color status output, ai-hooks JSON-validation refactor, log-trim memory opt |

A comprehensive **41-feature exercise matrix** (7 clusters + completeness critic)
was produced by an Understand-phase workflow and is the source of truth for the
per-feature steps. It is snapshotted into the repo as structured JSON (so it
survives session garbage-collection and stays machine-reproducible) at
[`exercise-matrix-2026-06-29.json`](./exercise-matrix-2026-06-29.json).

### Bias: do it right the first time

Per standing user guidance, this plan favors correctness and reversibility over
ship speed: validate before deploying, fix known-red state before pushing it
live, back up before overwriting, and back every "works" claim with real output.

---

## 2. Headline Finding (from analysis)

**`main` is very likely already RED.** The completeness critic reports that
`tests/bats/subagent_policy.bats` fails at the current tip: feature 363's new
`smoke-orchestrator` skill has no `subagents:` disposition in
`command_config.yml`, and feature 367's *dynamic* skill enumeration only catches
that gap **after** merge. Because the new **no-bypass CI gate** (`ci.yml`,
ranked the single highest-risk change) runs in that same lint job, the required
merge gate is currently failing.

This is a real, already-merged break — not a hypothetical. It is confirmed
empirically in **Phase A** (we trust nothing until the suite is run), and it is
the first fix-forward target.

---

## 3. Architecture — Four Sequential Phases

```text
Phase A   Baseline test (repo, pre-deploy)   ── must be green ──┐
  └ A.5   Fix-forward the reds (TDD, on-branch) ────────────────┘
Phase B   Backup live ~/.claude (+ symlink targets + ~/.manifest)
Phase C   Deploy: ./bootstrap.sh (full interactive)
Phase D   Re-validate the deployed environment (deploy-sensitive subset)
  └ D.5   Reconcile main <-> deployed (provisional until PR merges)
```

### Phase A — Baseline test (repo paths, before touching `~`)

Ordering matters (critic ordering-dependency list):

1. **`pyproject.toml` first** — it is the single backing config for three lint
   layers (edit-time `ruff check`, pre-commit ruff, CI changed-files gate).
   Validate it parses and that `pytest tests/python/` does **not** error under
   the new `--strict-markers --strict-config` (passes only because
   `pytest-asyncio` registers the `asyncio` marker; a bare runner would fail
   collection — flag, don't fix unless it bites).
2. **CI-mirror suite**: `shellcheck`, `yamllint`, `markdownlint`,
   `bats tests/bats/`, `pytest tests/python/`.
3. **Deep per-feature exercise** against repo paths, with
   `LIFECYCLE_STATE_DIR`, `LIFECYCLE_SMOKE_CMD`, `LIFECYCLE_PROVIDERS_CONFIG`
   overridden to tmp/repo paths so nothing pollutes `~/.manifest` or `~/.claude`.

**Exit condition**: full inventory of pass/fail with pasted evidence. Confirm or
refute the predicted `subagent_policy.bats` RED with a real run.

### Phase A.5 — Fix-forward the reds (do-it-right gate)

**Decision (approved): fix reds before deploying.** We never push a known-broken
state into live config. Each failure Phase A surfaces:

- Reproduce → write/adjust a failing test (TDD where applicable) → fix → green.
- Commit on branch `worktree-test-end-2-end`; roll all fixes into one PR.
- **Do not auto-merge.** The PR is the user's to merge.

Known first target: add a `subagents:` disposition for `smoke-orchestrator` to
`command_config.yml`; re-run `subagent_policy.bats` to green; re-run the whole
lint job to confirm the no-bypass gate would now pass.

### Phase B — Backup (reversibility before overwrite)

`bootstrap` deploys `configs/claude/settings.local.json`, which **overwrites the
live `~/.claude/settings.local.json`**, replacing any user-local hooks. It also
re-writes Cursor/Gemini/Codex/Antigravity targets.

- **The enumerated path list is authoritative** (not the intent phrase): back up
  `~/.claude`, `~/.cursor/rules`, `~/.gemini`, `~/.codex`, `~/.antigravity`, and
  `~/.manifest`, into a timestamped tarball `~/.claude.bak-<ts>.tar.gz`.
- **Full status manifest** (complete reference for the Phase C coverage check):
  `backup-manifest.txt` records **every** enumerated path with a status tag —
  `PRESENT <path>` (in the tarball) or `ABSENT <path>` (did not exist pre-run).
  The restore procedure recreates each `PRESENT` path from the tarball and
  `rm -rf`s each `ABSENT` path (e.g. if `~/.manifest` didn't exist pre-run,
  Phase D's real-default `init` creates it, and restore removes it to reach the
  true pre-run baseline).
- Record a documented restore command in the run log, listing exactly which paths
  it recreates and which it removes.

### Phase C — Deploy (approved: full interactive `./bootstrap.sh`)

Run `./bootstrap.sh` from the worktree, capturing full output. Watch the changed
deploy behaviors:

- rsync-resilient skill deploy — **note**: the cp fallback is effectively
  unreachable because `deploy_configs` hard-requires rsync and aborts first; we
  confirm rsync is present rather than validating dead code.
- `services.yml` additions; graphify gating
  (`deploy_configs → deploy_home_skills → gate_graphify_skill` order).
- New Cursor-rule deploy target: `~/.cursor/rules/graphify.mdc`,
  `~/.cursor/rules/lifecycle.mdc` (a deploy path separate from `~/.claude`).

If any deploy step fails mid-phase: **stop, report, offer restore-from-backup** —
do not press on.

**Post-deploy backup-coverage check** (closes the "enumeration may diverge" gap):
after `bootstrap.sh` completes, diff the set of paths it actually wrote (from its
output / a `find -newer` against the run start) against `backup-manifest.txt`.
Flag any written path **not** covered by the backup before proceeding to Phase D;
if found, extend the backup (or stop and report) rather than validating an
unbackable deploy.

### Phase D — Re-validate the deployed environment

**Selection criterion** (resolves the "which subset?" question): Phase D
re-exercises **only deploy-sensitive features** — those whose behavior changes
when paths resolve to `~/.claude`/`~/.cursor`/`~/.manifest` instead of the
repo/tmp paths used in Phase A. Features that are path-independent (pure logic
already proven in Phase A) are **not** re-run; they are listed under "Phase D
intentionally skips" below so the omission is deliberate, not accidental.

Deploy-sensitive features (re-exercise against real deployed paths):

- `~/.claude/scripts/lifecycle.sh` smoke-backed Verify/Implement gates (defaults
  to `~/.claude/scripts/smoke_test.py` + `~/.claude/config/lifecycle_providers.yml`)
  — this is the deploy-sensitive part (default path resolution).
- Deployed `lint_on_edit_hook.sh` firing on a deliberately-bad edit (requires the
  deployed `settings.local.json` hook wiring — hence the Phase B backup of any
  user-local hooks).
- Deployed skills present and well-formed (`graphify`, `lifecycle`,
  `smoke-orchestrator`); Cursor rules present at `~/.cursor/rules/*.mdc`.
- `parallel_agent.py` orchestration round-trip (OAuth CLI fallback).
- `check_status.sh` / `health-check` semantic colors + graphify D4 reporting
  (graphify reported as a managed tool, **not** counted toward orchestration
  readiness).

`~/.manifest` handling: only lifecycle `init` is exercised in Phase D (it's the
deploy-sensitive one — it creates the default `~/.manifest` tree). Phase D does
**one** real-default `init` to confirm the post-deploy tree is created
`0700`/files `0600`, then prunes **only that test track**:

- If `~/.manifest` was **ABSENT** pre-run: `rm -rf ~/.manifest` (the whole tree
  is test-created; safe to remove — matches the restore sentinel).
- If `~/.manifest` **existed** pre-run with real state: remove **only** the
  specific test track dir (`rm -rf ~/.manifest/lifecycle/state/<test-track>.json`),
  never the tree — user state is preserved and is also in the Phase B backup.

`status`/`anchor` are **not** re-run in Phase D — pointed at a tmp
`LIFECYCLE_STATE_DIR` they are path-independent and fully proven in Phase A, so
they are Phase-A-only (see the §4 table). All other lifecycle state-writing
exercises keep `LIFECYCLE_STATE_DIR` on a tmp dir (as in Phase A).

**Phase D intentionally skips** (path-independent, fully proven in Phase A):
lifecycle `decide`/`gate` pure decision core; the ai-hooks JSON-validation
refactor (fail-open logic is path-independent); `pyproject.toml`/ruff config
validation; all spec/doc/template lint checks; `subagent_policy.bats` (CI-suite,
not deploy-path-dependent). One line each: these exercise no `~/.claude`-resolved
path, so a green Phase A is sufficient evidence.

### Phase D.5 — Reconciliation (main ↔ deployed)

Phase C deploys from `worktree-test-end-2-end`, which carries the A.5 fixes that
are **not yet merged to `main`** (fix-forward PR is the user's to merge). To keep
the bias toward a consistent, reversible state, the deployed env is treated as
**provisional** until the PR merges:

- **If the user merges the fix-forward PR**: re-run `./bootstrap.sh` from `main`
  (or confirm the worktree tip now equals `main`) so `~/.claude` and `main` are
  identical — no lingering divergence.
- **If the user delays**: the run log records the exact deployed SHA and the open
  drift window; `~/.claude` runs branch code until merge. Acceptable short-term.
- **If the user abandons the PR**: restore from the Phase B backup to return
  `~/.claude` to its pre-deploy (pre-divergence) state.

This closes the gap the spec review flagged: there is now a defined path to a
state where `main` and `~/.claude` are consistent regardless of the merge outcome.

---

## 4. Per-Feature Exercise Matrix (risk-ranked highlights)

The full 41-feature matrix lives in
[`exercise-matrix-2026-06-29.json`](./exercise-matrix-2026-06-29.json) (structured
JSON: `clusters[].features[]` + `critic`). That file is the **feature inventory**
(what changed + how to drive it); **phase routing (A vs D) is owned by this
design**, not the matrix — the `Phase` column below and Phase D's "intentionally
skips" list are authoritative. Highest-leverage rows:

| Feature | Phase | Exercise (concrete) | Expected "works" |
|---|---|---|---|
| `subagent_policy.bats` gate | A | `bats tests/bats/subagent_policy.bats` | After A.5 fix: all checks green incl. `smoke-orchestrator` |
| no-bypass CI gate (`ci.yml`) | A | inspect changed-files step; validate on a real multi-commit PR push | gate fails on a planted fixable-only violation, passes when clean |
| `pyproject.toml` (new) | A | `pytest tests/python/ --collect-only -q` | collects (≈422) without `--strict-markers` error |
| lifecycle `decide`/`gate` | A | feed garbage + skip-ahead + runner-EMPTY signal JSON | `decide` always exit 0; `gate` maps allow/warn/refuse → 0/3/1 |
| lifecycle `init` | A + D | A: init 6 provider URL shapes into a tmp `LIFECYCLE_STATE_DIR`; D: one real-default `init` then prune that test track | correct provider parse; state dir 0700, files 0600; idempotent re-init |
| lifecycle `status`/`anchor` | A | exercise against a tmp `LIFECYCLE_STATE_DIR` (path-independent) | status table + `--json` round-trip; anchor re-emits phase line; exit 2 on missing track |
| `lint_on_edit_hook.sh` | A + D | A: run against repo path; D: trigger on a bad vs good edit via deployed hook wiring | advisory lint output on bad edit; silent on clean; fail-open |
| ai-hooks JSON refactor (`pr_create_trigger.py`, `cli_wrapper`, `tool_config`, `unified_hook`) | A | feed `{}`/whitespace/array/garbage/primitive | every case rc=0 fail-open; non-dict coerced, no traceback |
| graphify skill + `check_status.sh` D4 | D | `/graphify` preflight; `check_status.sh` against deployed skills | reports graphify as managed tool, not orchestration agent |

Each row asserts a concrete output/exit code — never merely "the unit test
passed."

---

## 5. Ordering Dependencies (must respect during execution)

1. Validate `pyproject.toml` / `ruff` config **before** any of the three lint
   layers (they silently diverge if it's wrong).
2. `subagent_policy.bats` is RED → fix in A.5 **before** asserting CI green.
3. `lint_on_edit_hook.sh` only fires after bootstrap copies scripts **and**
   deploys `settings.local.json` (which overwrites user-local hooks → Phase B
   backup).
4. `/lifecycle` smoke defaults (`~/.claude/...`) resolve only post-deploy →
   exercise via env-var overrides in Phase A, real paths in Phase D.
5. graphify gating runs `deploy_configs → deploy_home_skills → gate_graphify_skill`.
6. Cursor command surface must stay lockstep across `command_categories.yml`,
   `commands-index.mdc`, the new `.mdc` rules, and `docs/COMMANDS.md`
   (`commands_doc_drift.bats` / `help_coverage.bats` enforce).

---

## 6. Error Handling & Verification Standard

- **Evidence before assertions.** Every "works" is backed by pasted real output
  or exit code.
- **Fail-stop on errors after the live overwrite** (Phase C deploy **and** Phase
  D validation): the moment a deploy step fails or a deploy-sensitive exercise
  reveals a broken live environment, **stop further steps, report with evidence,
  and offer restore-from-Phase-B-backup**. Do **not** attempt ad-hoc fixes
  against live `~/.claude` — a Phase D failure means the live config is in a
  known-bad state, so the defined action is restore (or a deliberate, reported
  fix-forward decision), never improvisation.
- **No auto-merge.** Fix-forward lands as a reviewable PR.

---

## 7. Out of Scope (YAGNI)

- No refactoring beyond what a found failure requires.
- No graphify CLI install (`uv tool install`) unless the user already uses it.
- No edits to spec/doc-only files beyond lint validation.

---

## 8. Success Criteria

1. Phase A inventory complete; all reds fixed and the full suite green on-branch.
2. Live `~/.claude` backed up with a verified restore path.
3. `./bootstrap.sh` completes cleanly; deployed artifacts present.
4. Every Phase D (deploy-sensitive) feature exercise passes with pasted
   evidence; intentionally-skipped features documented.
5. Fix-forward PR opened (not merged); run log summarizes evidence per phase and
   records the deployed SHA + reconciliation path (D.5).
