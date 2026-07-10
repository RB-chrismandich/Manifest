# Implementation Plan: Critic-Driven Development Loop (CDDL)

**Branch**: `482-critic-dev-loop` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/482-critic-dev-loop/spec.md`

## Summary

CDDL adds a critic-gated implementation path: a re-entrant Python state machine
(`cddl_loop.py` + `configs/claude/scripts/cddl/` package) resolves a speckit or
superpowers feature via the existing `spec_review.sh` discovery seam, runs a bounded
clarification gate (both critics must emit structured completion signals), then a
bounded implement→verify→critique loop where an implementer role produces file-block
candidates, project gates run first, and two critics must each return a strict fenced
`cddl-verdict` JSON approval before changes are staged (staged = approved). Roles are
editable prompt files in `configs/claude/prompts/cddl/` (zero-touch deploy), invoked
via `claude -p --model <alias>` with stdin prompts behind the injectable `CDDL_CLI`
seam. Exposed as the dual-workflow skill `/spec-implement-loop`, which wraps the
re-entrant subcommands into one conversational session: the skill runs `start`,
relays any phase-1 questions to the operator, and re-invokes `answer` with their
responses until the gate resolves; driving `cddl_loop.py` directly uses the same
subcommands manually (research D6). All design decisions and rejected alternatives:
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11+ (ruff target py311; CI pytest on 3.14) for the
orchestrator including the entry shim `cddl_loop.py`, which satisfies the repo's
entry-point script conventions (`--help`, err()-style stderr, exit-code contract)
in Python — the `smoke_test.py` precedent; Bash appears only at the sourced
`spec_review.sh` discovery seam

**Primary Dependencies**: stdlib + PyYAML (already a repo dependency); runtime:
authenticated `claude` CLI (behind `CDDL_CLI` seam), `configs/claude/scripts/spec_review.sh`
(sourced discovery functions), `configs/claude/scripts/audit_log.sh` (audit writer),
`git`. No new third-party packages.

**Storage**: JSON + markdown files under
`${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/` (chmod 700,
keep-everything per clarification); audit JSONL at `~/.claude/cddl_audit.jsonl`
(the repo's per-tool audit convention — precedent `auto_issue_dev_audit.jsonl`;
env-overridable, via audit_log.sh, fail-open — the FR-017 audit exemption)

**Testing**: pytest (`tests/python/cddl/`, injected fake runner), bats
(`tests/bats/cddl_loop.bats`, PATH-stubbed `claude`), one Lite-tier smoke entry in
`smoke-catalog/manifest.yaml` (hermetic fixture repo + stub CLI)

**Target Platform**: macOS + Linux developer machines (same matrix as bootstrap)

**Project Type**: CLI tool + config assets inside the existing Manifest monorepo
(script package, prompt files, skill, config registration)

**Performance Goals**: pre-flight (discovery + git + role validation) < 5 s;
defaults: per-invocation timeout 600 s, whole-run wall clock 3 600 s, clarification
rounds 3, iteration ceiling 10 (all env/flag-configurable)

**Constraints**: ARG_MAX-safe prompts (stdin, contexts may reach hundreds of KB);
offline-testable (no network in unit/bats tests); fail-closed verdict parsing; no
writes outside target repo working tree except the run-state root and the audit
JSONL (`audit_log.sh` convention, exempted by spec FR-017); no
commit/push/merge ever; frontmatter fits the 22 000-byte aggregate skill budget
(~834 bytes headroom) at deployed size

**Scale/Scope**: single operator, one run per target repo at a time (stale-aware
lock, `loop_lock.sh` pattern); runs retained indefinitely (operator-managed pruning)

## Constitution Check

*GATE: evaluated pre-Phase 0 and re-checked post-Phase 1 design — PASS (one logged
lifecycle advisory, below).*

- **I. Configuration-as-Code — PASS**: every asset is repo-sourced and deployed by
  the existing bootstrap rsync (`prompts/cddl/` needs zero bootstrap changes; skill
  via `deploy_home_skills`); nothing is hand-edited in `~/.claude/`.
- **II. Parallel Agent Orchestration — PASS (process gate)**: this feature touches
  security-sensitive surface (subprocess invocation, LLM-driven file writes, path
  containment) and exceeds 200 lines, so its PRs require parallel-agent
  cross-verification; the lifecycle's `/spec-review --mode technical` (phase 7) runs
  before implementation. Runtime note: CDDL's unanimous two-critic verdicts are a
  deliberate, spec-declared distinct mechanism (Out of Scope), not a replacement for
  `parallel_agent.py` consensus on PRs.
- **III. Consensus-Driven Decisions — PASS**: PR validation for this feature uses the
  standard thresholds; CDDL itself performs no consensus scoring (unanimous
  structured verdicts, documented in spec Out of Scope).
- **IV. Skill-First Extensibility — PASS**: capability lands as the discrete skill
  `spec-implement-loop` + standalone script package; nothing is absorbed into
  `parallel_agent.py`/`agents/`.
- **V. Bootstrap Reproducibility — PASS**: no bootstrap logic changes at all; the
  deploy remains idempotent by the existing rsync/no-delete mechanism.
- **VI. State-Gated Lifecycle — ADVISORY (logged override)**: Specify (done) →
  Clarify (done, 5 Qs) → **Spec-Review (product): skipped** — the operator invoked
  `/speckit-plan` directly; human-driven work proceeds on advisory warning with this
  logged override. Recommendation: run `/spec-review --mode product` before
  `/speckit-tasks`. Second logged override (2026-07-10, /speckit-analyze): phase-5
  hierarchy provisioning (`/speckit-taskstoissues`) deferred — tasks tracked in
  tasks.md only; run it before `/speckit-implement` if issue-tier tracking is
  wanted. Third logged override (2026-07-10, /speckit-implement): phase-7
  Spec-Review (technical) skipped — operator invoked `/speckit-implement` directly
  after the analyze gate passed with 0 critical findings; recommendation stands to
  run `/spec-review --mode technical` on the diff before the PR merges (Principle II
  cross-verification applies at PR time regardless). Remaining phases map: Plan (this) → Tasks → Analyze →
  Spec-Review (technical) → Implement → Verify, where Verify includes the new
  Lite-tier smoke entry (D13) so the shipped workflow has critical-path smoke
  coverage.

**Post-Phase-1 re-check**: design artifacts introduce no new violations — no new
projects, no new dependencies, no bootstrap surface; spec amendments from D3
(SC-008 / deploy edge cases retargeted to the prompts namespace) are logged in the
spec's Clarifications section.

## Project Structure

### Documentation (this feature)

```text
specs/482-critic-dev-loop/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (D1–D13 decisions)
├── data-model.md        # Phase 1 output (entities, states, validation)
├── quickstart.md        # Phase 1 output (operator walkthrough)
├── contracts/           # Phase 1 output
│   ├── cli-interface.md     # cddl_loop.py commands, flags, env, exit codes
│   ├── verdict-format.md    # fenced cddl-verdict JSON contract
│   ├── role-definition.md   # role frontmatter schema
│   └── candidate-format.md  # implementer file-block grammar + confinement
├── checklists/requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
configs/claude/
├── prompts/cddl/                    # role definitions (zero-touch rsync deploy; D3)
│   ├── implementer.md               # frontmatter: name/description/model + prompt body
│   ├── qa-critic.md
│   └── arch-critic.md
└── scripts/
    ├── cddl_loop.py                 # entry shim: --help, err(), exit-code contract
    └── cddl/                        # orchestrator package (D1)
        ├── __init__.py
        ├── cli.py                   # subcommands start/answer/status; arg parsing
        ├── context.py               # discovery via spec_review.sh seam (D2)
        ├── roles.py                 # role-definition load + frontmatter validation
        ├── invoke.py                # CDDL_CLI seam, stdin prompts, timeouts (D4, D11)
        ├── verdicts.py              # fenced-block strict parser, fail-closed (D5)
        ├── loop.py                  # two-phase state machine (D6)
        ├── candidate.py             # file-block parse, confinement, atomic apply (D10)
        ├── gitops.py                # preflight, default-branch/dirty checks, staging (D9)
        ├── verify.py                # project-gate auto-detect + --verify-cmd (D8)
        └── persistence.py           # run dirs, state.json, report.md, audit (D7)

.skillshare/skills/spec-implement-loop/SKILL.md   # user-facing skill (D12)
configs/claude/config/command_config.yml          # + tool_policies entry (D12)
smoke-catalog/manifest.yaml                       # + cddl Lite smoke entry (D13)

tests/
├── python/cddl/                     # test_loop, test_verdicts, test_candidate,
│   │                                #   test_context, test_gitops, test_verify,
│   └── conftest.py                  #   test_persistence (fake-runner fixtures)
└── bats/cddl_loop.bats              # CLI-level: --help, exit codes, discovery, stub claude

# Regenerated derived artifacts (never hand-edited):
configs/cursor/rules/*.mdc, docs/COMMANDS.md, GEMINI/AGENTS command-index blocks
```

**Structure Decision**: single-project layout inside the existing monorepo, mirroring
the `smoke_test.py` → `smoke_orchestrator/` entry-shim-plus-package precedent; role
prompts under the already-deployed `prompts/` tree; skill in the `.skillshare/skills/`
source of truth. No new top-level directories.

## Phase 2 Approach: Task Generation

Tasks are deliberately not embedded here — `/speckit-tasks` produces
`specs/482-critic-dev-loop/tasks.md` as the next lifecycle phase (after the
recommended `/spec-review --mode product`). Generation inputs and ordering:

- **Derivation**: one task cluster per orchestrator module in Project Structure
  (context → roles → invoke → verdicts → candidate → gitops → verify →
  persistence → loop → cli), each traced to its contract
  (`contracts/*.md`) and data-model entities.
- **Ordering**: test-first per repo convention — pytest fixtures/fakes before
  module implementation; leaf modules (verdicts, candidate, roles) before the
  state machine (loop) and CLI wiring; skill + config registration + smoke
  entry + derived-artifact regeneration last.
- **Gate**: `/spec-audit-tasks` runs after implement (speckit after_implement
  hook) to verify every generated task completed.

## Complexity Tracking

No Constitution Check violations to justify. (The Principle VI product-review skip is
a logged human-driven advisory override, recorded above, not a complexity violation.)
