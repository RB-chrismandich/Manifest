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
per-feature steps. Persisted at the session task output:
`…/tasks/w31o3dbuz.output`.

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

```
Phase A   Baseline test (repo, pre-deploy)   ── must be green ──┐
  └ A.5   Fix-forward the reds (TDD, on-branch) ────────────────┘
Phase B   Backup live ~/.claude (+ symlink targets)
Phase C   Deploy: ./bootstrap.sh (full interactive)
Phase D   Re-validate the deployed environment
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

- Snapshot to a timestamped tarball: `~/.claude.bak-<ts>.tar.gz` covering
  `~/.claude` plus the symlink-target trees touched by deploy
  (`~/.cursor/rules`, `~/.gemini`, `~/.codex`, `~/.antigravity`).
- Record a documented one-line restore command in the run log.

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

### Phase D — Re-validate the deployed environment

Re-exercise each feature against the **deployed** `~/.claude` paths now that the
defaults resolve:

- `~/.claude/scripts/lifecycle.sh` smoke-backed Verify/Implement gates (defaults
  to `~/.claude/scripts/smoke_test.py` + `~/.claude/config/lifecycle_providers.yml`).
- Deployed `lint_on_edit_hook.sh` firing on a deliberately-bad edit (requires the
  deployed `settings.local.json` hook wiring — hence the Phase B backup of any
  user-local hooks).
- Deployed skills present and well-formed (`graphify`, `lifecycle`,
  `smoke-orchestrator`); Cursor rules present.
- `parallel_agent.py` orchestration round-trip (OAuth CLI fallback).
- `check_status.sh` / `health-check` semantic colors + graphify D4 reporting
  (graphify reported as a managed tool, **not** counted toward orchestration
  readiness).

---

## 4. Per-Feature Exercise Matrix (risk-ranked highlights)

The full 41-feature matrix lives in the workflow output. Highest-leverage rows:

| Feature | Exercise (concrete) | Expected "works" |
|---|---|---|
| `subagent_policy.bats` gate | `bats tests/bats/subagent_policy.bats` | After A.5 fix: all checks green incl. `smoke-orchestrator` |
| no-bypass CI gate (`ci.yml`) | inspect changed-files step; validate on a real multi-commit PR push | gate fails on a planted fixable-only violation, passes when clean |
| `pyproject.toml` (new) | `pytest tests/python/ --collect-only -q` | collects (≈422) without `--strict-markers` error |
| lifecycle `decide`/`gate` | feed garbage + skip-ahead + runner-EMPTY signal JSON | `decide` always exit 0; `gate` maps allow/warn/refuse → 0/3/1 |
| lifecycle `init`/`status`/`anchor` | init 6 provider URL shapes into a tmp `LIFECYCLE_STATE_DIR` | correct provider parse; state dir 0700, files 0600; idempotent re-init |
| `lint_on_edit_hook.sh` | trigger on a bad vs good edit (post-deploy) | advisory lint output on bad edit; silent on clean; fail-open |
| ai-hooks JSON refactor (`pr_create_trigger.py`, `cli_wrapper`, `tool_config`, `unified_hook`) | feed `{}`/whitespace/array/garbage/primitive | every case rc=0 fail-open; non-dict coerced, no traceback |
| graphify skill + `check_status.sh` D4 | `/graphify` preflight; `check_status.sh` | reports graphify as managed tool, not orchestration agent |

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
- **Fail-stop on deploy errors** (Phase C): report and offer restore, don't
  improvise.
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
4. Every Phase D feature exercise passes with pasted evidence.
5. Fix-forward PR opened (not merged); run log summarizes evidence per phase.
