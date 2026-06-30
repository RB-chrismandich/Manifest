# Implementation Plan: Deploy Reconciliation Review (Orphan Detection)

**Branch**: `368-deploy-orphan-review` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/368-deploy-orphan-review/spec.md`

## Summary

Add a **deploy reconciliation review** that compares what Manifest has deployed into the
five assistant homes (`~/.claude` + the mirrored `~/.cursor ~/.gemini ~/.codex
~/.antigravity`) against what the project would currently deploy, and reports deployed
units with no project source as **KEEP** (protected) or **REMOVE** (orphan). Three slices
deliver the spec:

1. **On-demand preview (US1/P1, MVP)** — a new `configs/claude/scripts/deploy_reconcile.sh`
   (modeled on `branch_clean.sh`: dry-run preview by default) lists KEEP/REMOVE orphans with
   reasons + summary counts; read-only, `--json` available. Wrapped by a new `/deploy-reconcile`
   skill (Skill-First, P-IV).
2. **Deploy-time report (US2/P2)** — a fail-open `reconcile_deploy_report()` in
   `bootstrap/lib/deploy.sh`, called from `bootstrap.sh main()` after `deploy_configs`, runs
   the script in **preview-only** mode and prints a one-line KEEP/REMOVE summary. It never
   deletes and never fails the deploy (P-V).
3. **Opt-in recoverable removal (US3/P3)** — `--remove` (+ confirm / `--yes`) *moves* REMOVE
   orphans to a timestamped backup under `~/.manifest/reconcile-trash/<ts>/` with a generated
   `restore.sh`; never hard-deletes; KEEP items untouched.

Detection is **stateless** (current deployed vs current project), dedups shared symlinked
targets by `python3 os.path.realpath` (one verdict per canonical path), and bounds
active-dependent detection to a reverse-symlink scan of the four secondary homes. Full
decision record: [research.md](./research.md); entities: [data-model.md](./data-model.md);
interface: [contracts/reconcile-cli.md](./contracts/reconcile-cli.md) +
[contracts/deploy-integration.md](./contracts/deploy-integration.md); verification walkthrough:
[quickstart.md](./quickstart.md).

## Technical Context

**Language/Version**: Bash (macOS Bash 3.2-compatible, `set -euo pipefail`) for
`deploy_reconcile.sh` + the `bootstrap/lib/deploy.sh` hook; `python3` (already a repo
dependency) for portable `os.path.realpath`, `fnmatch.fnmatchcase` glob matching, and YAML
policy parsing invoked inline from Bash; YAML for `reconcile.yml`.

**Primary Dependencies**: existing bootstrap libraries (`bootstrap/lib/deploy.sh`,
`common.sh`: `link_shared_assets`, `create_symlink`, `restore_runtime_state`,
`verify_installation`); `branch_clean.sh`/`label_sync.sh` as the CLI-shape precedent;
`smoke_orchestrator` (`smoke_test.py`) for the P-VI Verify gate. No new third-party deps.

**Storage**: Stateless — no database, no deploy-history. On-disk artifacts are only: the
committed protection policy `configs/claude/config/reconcile.yml` (auto-deployed to
`~/.claude/config/`), the recoverable removal backup tree under `~/.manifest/reconcile-trash/`
(outside managed scope), and the optional `--json` stream the caller redirects.

**Testing**: `bats` (`tests/bats/deploy_reconcile.bats`, ~15 cases over a hermetic mktemp
managed-home fixture); optional `pytest` (`tests/python/test_reconcile_policy.py`) only if the
classifier is factored into a python3 helper; the P-VI Verify gate ships the repo's **first**
smoke catalog `smoke-catalog/manifest.yaml` (app `manifest`, tier `Lite`, type `cli`) run via
`smoke_test.py run --app manifest --tier Lite`.

**Target Platform**: Developer machines (macOS Intel/Apple Silicon, Linux) where Manifest is
deployed via `bootstrap.sh`; Ubuntu GitHub Actions runners for CI/smoke.

**Project Type**: Single project — CLI / configuration-management repo (agent-orchestration
configs deployed to `~/` via `bootstrap.sh`).

**Performance Goals**: On-demand review bounded by `find -type f` over the five homes plus
~20 realpath calls (the dependent-edge scan is `find -mindepth 1 -maxdepth 2 -type l` over the
four secondary homes only). Deploy-time report adds negligible cost vs the deploy's full-tree
rsync + existing `list_deployed_files` `find` (SC-006 — "no perceptible delay").

**Constraints**: report-only by default and at deploy time (FR-006); deploy hook is fail-open
(`|| print_warning`) and never contributes to `verify_errors` (P-V); Bash 3.2-safe; portable
realpath via `python3` (never `readlink -f` — BSD/macOS lacks `-f`); `err() { echo
"deploy-reconcile: $*" >&2; }`; `--help` ≤15 lines and succeeds before any config/home/project
lookup; orphans-found NEVER yields a nonzero exit; recoverable removal only (no hard delete by
default); no manual edits to deployed `~/.claude` (source in `configs/`, machine-local override
at `~/.manifest`).

**Scale/Scope**: 5 managed roots; ~5 cross-home parent-dir symlinks per secondary home (~20
edges total); ~70+ skills + per-home config files as deployable units; deployable-unit
granularity (skill = top-level dir, config = file).

**Unknowns**: None open. Phase 0 resolved all seven research topics (the two research agents
that errored on the structured-output cap — managed-scope enumeration and expected-set
derivation — are fully covered by Topics 1/2 (managed roots + protection boundary) and Topic 5
(`--project` source enumeration honoring `services.yml`)). The five cross-topic contradictions
and the design-artifact JSON/format contradictions surfaced by review were reconciled (see
research.md §Verification; data-model §9 now defers to the contract as the single source of
truth for the wire format).

## Constitution Check

*GATE: Must pass before Phase 0. Re-checked after Phase 1 (below).*

| Principle | Verdict | Notes / Gate |
|---|---|---|
| I. Configuration-as-Code | **PASS** | Script → `configs/claude/scripts/deploy_reconcile.sh`; policy → `configs/claude/config/reconcile.yml` (auto-deploys via `rsync config/`, deploy.sh:144); skill → `.skillshare/skills/deploy-reconcile/`. Machine-local override at `~/.manifest/reconcile.local.yml` (outside `~/.claude`), so users add protections without editing the deployed tree. The feature **is** drift correction and is *complementary* to `./bootstrap.sh --reconfigure`: reconfigure re-asserts what *should* exist; this prunes what *should not*. Removal is a sanctioned, recoverable reconciliation (move-aside), not a prohibited manual `~/.claude` edit. |
| II. Parallel Agent Orchestration | **APPLIES (obligation at PR)** | Implementation performs destructive file removal (security-sensitive) and the aggregate diff exceeds 200 lines → the PR MUST be cross-verified by ≥2 agents via `parallel_agent.py` before merge. (Planning already used a multi-agent workflow with an adversarial verify pass.) Discharged at `/speckit-implement-review` + PR. |
| III. Consensus-Driven Decisions | **PASS (deferred to review)** | Cross-verification at PR time must meet the ≥80 / 50–79 / <50 thresholds; document any bypass. |
| IV. Skill-First Extensibility | **PASS** | New user capability is the `/deploy-reconcile` skill wrapping a dedicated script (branch-clean precedent). No behavior added to `parallel_agent.py` or other core scripts. |
| V. Bootstrap Reproducibility | **PASS** | Deploy-time call is guarded `reconcile_deploy_report || print_warning …` under `set -e` (fail-open); it is pure-read preview (idempotent), never creates a backup dir at deploy, and never increments `verify_errors` — bootstrap still exits non-zero solely on real verify failure. Script deploy is an idempotent copy + `chmod +x`. |
| VI. State-Gated Lifecycle | **PASS w/ obligations** | Feature flows through all nine phases in order (currently at Plan→Tasks). The **Verify gate is the smoke test**: `smoke-catalog/manifest.yaml` (tier Lite, cli) MUST exist and exit 0 before any unit of work is marked complete — `tasks.md` MUST include building it (missing coverage is never a pass). Review/analyze gates use the APPROVED/NEEDS_REVIEW/BLOCKED model. |
| Quality Gates / Dev Workflow | **PASS w/ obligations** | New shell script REQUIRES `bats` coverage; `shellcheck deploy_reconcile.sh` + the bootstrap hook; `yamllint reconcile.yml` + the smoke catalog; `docs/COMMANDS.md` is **regenerated** from SKILL.md via `generate_commands_doc.py` (never hand-edited); CI stays green and keeps its test floor. |

**Result**: No violations requiring Complexity Tracking. Gate II is an obligation discharged at
review/PR; Gate VI's smoke artifact is an explicit task, not a design blocker.

## Project Structure

### Documentation (this feature)

```text
specs/368-deploy-orphan-review/
├── spec.md              # Feature spec (clarified: Session 2026-06-30)
├── plan.md              # This file
├── research.md          # Phase 0 decision record (7 topics + Verification)
├── data-model.md        # Phase 1: 9 entities; §9 defers to contract for wire format
├── quickstart.md        # Phase 1: hermetic 7-step verification walkthrough
├── contracts/
│   ├── reconcile-cli.md          # AUTHORITATIVE interface: flags, stdout, --json schema, exit codes
│   └── deploy-integration.md     # Deploy-time fail-open report-only contract
└── checklists/
    └── requirements.md  # Spec quality checklist (passing)
```

### Source Code (repository root)

```text
configs/claude/
├── scripts/
│   └── deploy_reconcile.sh         # NEW — reconcile engine: preview default, --remove (recoverable), --json
├── config/
│   ├── reconcile.yml               # NEW — protection policy (flat reconcile.protected: glob list)
│   └── command_config.yml          # MODIFIED — add tool_policies.deploy-reconcile (Bash; parallel_agents conditional; subagents never)

.skillshare/skills/deploy-reconcile/
└── SKILL.md                        # NEW — /deploy-reconcile (Preview → Apply-with-confirm → Review → Safety)

bootstrap/lib/deploy.sh             # MODIFIED — add fail-open reconcile_deploy_report()
bootstrap.sh                        # MODIFIED — call reconcile_deploy_report (guarded) in main() after deploy_configs

smoke-catalog/
└── manifest.yaml                   # NEW — first smoke catalog: app manifest, tier Lite, cli (P-VI Verify gate)

tests/bats/
└── deploy_reconcile.bats           # NEW — ~15 cases over a hermetic mktemp managed-home fixture
tests/python/
└── test_reconcile_policy.py        # NEW (optional) — only if classifier is factored into a python3 helper

docs/COMMANDS.md                    # MODIFIED — regenerated from SKILL.md (generate_commands_doc.py), never hand-edited
.github/workflows/ci.yml            # MODIFIED — wire smoke_test.py --app manifest --tier Lite (Verify gate) if not already
```

**Structure Decision**: Single-project layout. The deployable runtime artifacts (the script,
the policy YAML, the skill) live under `configs/` and `.skillshare/skills/` per
Configuration-as-Code; the bootstrap integration lives in `bootstrap/lib/` + `bootstrap.sh`;
the smoke catalog is a new repo-root `smoke-catalog/` (the orchestrator's default catalog dir);
tests follow the repo's bats-first convention for shell/deploy logic.

## Phase 0 — Research

All decisions consolidated in [research.md](./research.md) (decision / rationale /
alternatives / file:line evidence / risks), produced by a parallel research panel and an
adversarial verification pass that resolved 5 cross-topic contradictions (config location,
trash-root variable `MANIFEST_STATE_ROOT` not `_DIR`, script filename `deploy_reconcile.sh`,
the `--home` hermetic hook, env-naming). No open unknowns remain.

## Phase 1 — Design & Contracts

- Entities (9, stateless/in-memory) → [data-model.md](./data-model.md)
- Authoritative interface (flags, stdout, `--json` schema, exit codes) →
  [contracts/reconcile-cli.md](./contracts/reconcile-cli.md)
- Deploy-time fail-open report-only contract → [contracts/deploy-integration.md](./contracts/deploy-integration.md)
- Verification walkthrough → [quickstart.md](./quickstart.md)
- Post-design reconciliation: the divergent `--json` schema and preview format in
  data-model.md/quickstart.md were aligned to `contracts/reconcile-cli.md` (now the single
  source of truth for the wire format and stdout).
- Agent context: the `<!-- SPECKIT START/END -->` block in `CLAUDE.md` is updated to point here.

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1: the design introduces no new principle violations. The skill +
dedicated script keep Principle IV intact; the fail-open, report-only deploy hook keeps
Principle V intact (idempotent, never aborts, never touches `verify_errors`); the policy and
script are Configuration-as-Code with a machine-local override outside `~/.claude` (Principle
I). Standing obligations: the Gate II parallel-agent cross-verification at PR time, and the
Gate VI smoke artifact (`smoke-catalog/manifest.yaml`) which must be built and pass. **No
Complexity Tracking entries required.**

## Complexity Tracking

No constitution violations — table intentionally empty. (The new top-level `smoke-catalog/`
directory is mandated by Principle VI's Verify gate, not an added abstraction.)
