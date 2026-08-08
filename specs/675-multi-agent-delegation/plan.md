# Implementation Plan: Multi-Agent Delegation Plugin

**Branch**: `675-multi-agent-delegation` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/675-multi-agent-delegation/spec.md`

## Summary

Ship a repo-native plugin bundle, `manifest-delegate`, that supersedes the
externally installed `openai/codex-plugin-cc` v1.0.6 in this workspace and
generalizes its capabilities — delegation/rescue with resumable follow-ups,
readiness check, second opinion, background job management
(status/result/cancel), session transfer, and an optional finish-time review
gate — across an extensible backend registry seeded with Codex, Claude, and
Antigravity. Technical approach (research.md D1–D11): a single self-contained
Python dispatcher inside the plugin drives one-shot CLI executions with
per-job record directories (no persistent broker); resumable follow-ups use
each CLI's native resume (`codex exec resume`, `claude -p --resume`,
`agy -p --conversation`); a declarative `backends.json` registry makes every
surface backend-generic; a user-level `~/.claude/config/delegation.{json,yml}`
(JSON canonical — setup writes `delegation.json`; YAML honored/written only
when PyYAML is importable) carries default backend, per-backend
enable/model/budget, and soft review-gate
settings (factory: codex default, 600s budget, gate off).

## Technical Context

**Language/Version**: Python 3.9+ — the oldest interpreter guaranteed on the
bootstrap-supported set (macOS Command Line Tools ships 3.9.x at
`/usr/bin/python3`; supported Linux releases ship ≥3.9). Dispatcher + hook
scripts are stdlib-only, syntax-constrained to 3.9 (no `match`/`case`, no
PEP 604 unions at runtime), and open with an early version probe that exits
with an exact remediation message on older interpreters (research.md D11);
verified by an install test on a machine without Manifest bootstrap.
Markdown skills/agent; JSON/YAML config. No Node runtime (baseline's Node
engine is replaced, not vendored).

**Primary Dependencies**: External CLIs invoked as subprocesses: `codex`
(npm `@openai/codex` / brew cask), `claude` (npm `@anthropic-ai/claude-code`),
`agy` (Antigravity IDE + `agy install`). Optional reads (degrade to compiled
factory defaults when absent, per SC-005): `~/.claude/config/parallel_agent.yml`
(`model_tiers`; PyYAML-if-importable, else tier passthrough),
`~/.claude/config/services.yml` (workspace disables; fixed-format extraction
of the generator-owned layout — never requires PyYAML),
`~/.claude/config/delegation.{json,yml}` (user config; JSON always, YAML when
PyYAML importable — research.md D3).

**Storage**: Per-job record directories under
`~/.claude/.agent_outputs/delegations/<workspace-slug>-<hash>/<job-id>/`
(`record.json`, `output.txt`, `job.log`), pruned keep-last-50 per workspace
(research.md D2). No database, no shared mutable index.

**Testing**: `pytest tests/python/` (dispatcher: registry loading, config
precedence, envelope normalization, job lifecycle, fault injection for SC-004);
`bats tests/bats/` (skill/bundle registration gates, `--help` coverage,
registry↔`cli_agents` drift test, hook wiring); smoke coverage per Constitution
VI for each shipped user-facing workflow (delegate, readiness, second opinion,
gate) via `smoke_test.py` catalog entries. Fault-injection matrix: missing
binary, unauthenticated, disabled-by-workspace, disabled-by-user, timeout,
malformed output, unknown backend.

**Target Platform**: macOS + Linux workstations (the bootstrap-supported set);
Claude Code is the primary harness; dispatcher is harness-neutral
(plain-shell invocable) so Cursor/Codex/agy harness sessions can call it.

**Project Type**: Monorepo plugin bundle (`plugins/manifest-delegate/`) +
repo registration surfaces + tests/docs.

**Performance Goals**: Readiness check < 30s wall-clock for all three backends
(SC-003; probes run in parallel with per-probe timeouts ≤ 10s). Delegation
spawn overhead < 2s beyond backend runtime. Default delegation budget 600s,
enforced with process-group termination (FR-012).

**Constraints**:
- Catalog budgets (measured 2026-08-05): catalog frontmatter 25110/29000
  (3890 free — two new descriptions fit); per-bundle cap 6000 (new bundle
  starts at 0); **cross-skill warning-ref ratchet 133/133 — zero headroom**:
  new skill bodies must add zero prose skill-references (file-path links only)
  or remove equal refs elsewhere; blocking-ref tier 0/35. Root `CLAUDE.md`
  byte budget 12707/12900 constrains the agent-context update.
- Harness routing: no model IDs or per-harness config in SKILL.md/agent
  frontmatter (`configs/claude/references/harness-routing.md`); tiers by name,
  resolved via `parallel_agent.yml` `model_tiers` when present.
- Non-autonomy (FR-008): read-only delegation by default; never
  `--dangerously-*` flags; gate never auto-applies fixes.
- First bundle in this repo to ship plugin `hooks/` (baseline proves Claude
  Code supports it; repo test apparatus gains a hook-wiring gate).

**Scale/Scope**: 3 seeded backends (registry-extensible), 2 skills, 1 agent,
3 hooks, 1 dispatcher (9 subcommands + hidden worker mode), 4 contracts, ~15 new files + 6
registration-surface edits + generator reruns.

## Constitution Check

*GATE: evaluated pre-Phase-0 and re-evaluated post-Phase-1 (both pass; see
re-check note at end of section).*

| Principle | Verdict | Evidence |
|---|---|---|
| I. Configuration-as-Code | PASS | All shipped artifacts live in `plugins/manifest-delegate/` + registration files, version-controlled. Runtime state (`.agent_outputs/delegations/`) and user config (`delegation.{json,yml}`) are user-scope files no deployer owns — explicitly blessed by V.4's note; nothing writes into deployed trees. |
| II. Parallel Agent Orchestration | PASS (obligation carried to implement phase) | This is an architectural change: the implementation PR MUST run `manifest parallel-agent` cross-verification (Tier 1) before merge; the plan records this as a task-phase gate. |
| III. Consensus-Driven Decisions | PASS | Applies at the implementation review gates; thresholds unchanged. |
| IV. Skill-First Extensibility | PASS | Capability ships as skills in a bundle; the dispatcher is new plugin-local code — `parallel_agent.py` is not expanded (D5 explicitly rejected absorbing it). Constitution's `.skillshare/` wording is stale (superseded by feature 674's `plugins/` layout, per SKILL-NAMING.md); we follow the current authoritative lifecycle. |
| V. Reproducible, Idempotent Deployment | PASS | Plugin distributed via the marketplace mechanism (674); repo `configs/` untouched except docs. `delegation.{json,yml}` is user state written only by the user (or by `delegate-setup` on explicit request, to the user-scope path — canonically `delegation.json`; YAML updated in place only when PyYAML is importable, research.md D3). Single ownership: no path is written by two mechanisms; job records are runtime output, not deployment. |
| VI. State-Gated Lifecycle | PASS with logged note | Phases 1–4 complete (spec, 5/5 clarifications, 16/16 requirements checklist, plan + design artifacts). Phase-3 product review ran 2026-08-05 — its findings were fixed into the artifacts, but the synthesizer artifact (`.spec-review/feedback.md`) recorded no verdict (known agy-stdin false-green); re-run the synthesizer before the phase-7 technical review gate is claimed. Phase 5: `/speckit-tasks` complete; hierarchy provisioning via `/speckit-taskstoissues` DEFERRED — **logged here as the Principle VI override record** (human-driven work): tracker issues will be provisioned before implementation begins. Phase 6: `/speckit-analyze` ran 2026-08-05 → 0 critical findings (gate PASS); 2 HIGH + 12 MEDIUM remediated into the artifacts same day. Phase 7: `/spec-review --mode technical` ran 2026-08-05 — panel: codex completed (5 findings: read-only enforceability, CAS locking, worker-crash reaper, envelope extraction contract, transfer-vocabulary scoping); agy returned NO_ISSUES in 14s (unreliable — known stdin false-green) and cursor/gemini failed (usage-limited/retired); the script's synthesizer false-greened again, so findings were synthesized from the raw agent outputs, all 5 adjudicated valid and fixed into the artifacts same day → **APPROVED** (single-reliable-reviewer caveat recorded; Constitution II's Tier-1 cross-verification gate still runs on the implementation PR, T050). Verify gate: each shipped workflow gets a critical-path smoke test, executed by T048's `smoke_test.py run --tier Lite` gate. |
| VII. Published Artifact Integrity | DORMANT/PASS | The bundle is consumed from the local checkout via the marketplace path `./plugins/manifest-delegate` — not a published package. If it is ever published, VII's pinning/scrubbing obligations activate (noted in MIGRATION.md). |

**Post-design re-check (after Phase 1)**: data-model.md and contracts/
introduce no new projects, no daemons, no second write-owner for any path, and
no model-ID hardcoding; skills remain the only user surface. No violations to
justify — Complexity Tracking is empty except the two deliberate novelties
noted there.

## Project Structure

### Documentation (this feature)

```text
specs/675-multi-agent-delegation/
├── plan.md              # This file
├── research.md          # Phase 0 (D1–D11 decisions + baseline inventory)
├── data-model.md        # Phase 1 (entities, states, validation)
├── quickstart.md        # Phase 1 (install → readiness → delegate → gate)
├── contracts/           # Phase 1
│   ├── delegate-cli.md                  # dispatcher subcommand contract
│   ├── result-envelope.schema.json      # FR-002 normalized result
│   ├── delegation-config.schema.json    # FR-013 user config
│   └── backend-registry.schema.json     # FR-016 registry entry
├── checklists/requirements.md           # (pre-existing, 16/16)
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
plugins/manifest-delegate/
├── .claude-plugin/plugin.json      # name/version/description + EXPLICIT skills array (repo rule)
├── MIGRATION.md                    # baseline→replacement map (13 rows) + uninstall + gate-exclusivity note
├── config/
│   └── backends.json               # extensible backend registry (D4, JSON: stdlib-parseable): codex, claude, antigravity
├── manifest_delegate/              # dispatcher implementation (D5, amended): stdlib-only package
│   ├── __init__.py                 # flat re-export facade; submodules are the patch targets
│   ├── constants.py                # paths, regexes, subcommand list, err()
│   ├── registry.py                 # backend-registry load + validation (D8)
│   ├── config.py                   # user config / services.yml / model tiers (D3)
│   ├── jobstore.py                 # job-record store (data-model.md)
│   ├── envelope.py                 # result-envelope normalization (SC-004)
│   ├── backend.py                  # argv building, tier/budget resolution, payload limits
│   ├── process.py                  # spawn, pgid tracking, drain, locks
│   ├── worker.py                   # background/foreground backend runs
│   ├── task.py review.py gate.py   # the delegating subcommands
│   ├── jobs_cli.py                 # status|result|cancel
│   ├── transfer.py                 # transcript validation + session handover (FR-015)
│   ├── readiness.py setup.py       # probes + `setup`
│   └── cli.py                      # parser + main()
├── scripts/
│   ├── delegate.py                 # executable entry (D5): version probe → sys.path → manifest_delegate; task|review|status|result|cancel|setup|transfer|gate|resume-candidate; --help first
│   ├── stop_gate_hook.py           # Stop hook → delegate.py gate (soft gate, D9)
│   └── session_hook.py             # SessionStart (env capture) / SessionEnd (capture eviction + orphan cleanup)
├── hooks/hooks.json                # Stop (900s; gate budget capped ≤840s) + SessionStart/SessionEnd (5s)
├── agents/delegate-runner.md       # thin forwarder agent, model: sonnet, tools: Bash
└── skills/
    ├── delegate/
    │   ├── SKILL.md                # delegation/second-opinion/follow-up/jobs/transfer entry
    │   └── references/
    │       ├── result-envelope.md  # FR-002 conventions (presentation rules)
    │       ├── prompting-codex.md  # D10 original guidance (not vendored)
    │       ├── prompting-claude.md
    │       └── prompting-agy.md
    └── delegate-setup/SKILL.md     # readiness + gate toggle + config guidance

# Registration-surface edits (existing files)
.claude-plugin/marketplace.json                  # + manifest-delegate entry (category: productivity)
configs/claude/config/skill_policies.yml         # + bundle block (2 skills), expected_total 114 → 116
configs/claude/config/command_config.yml         # + tool_policies: delegate, delegate-setup
CLAUDE.md                                        # SPECKIT block → this plan (≤12900 bytes)
smoke-catalog/manifest.yaml                      # + delegate/readiness/second-opinion/review/gate smoke entries (T017/T021/T025/T029/T037)
configs/claude/config/reconcile.yml              # + delegation.* protected glob (user config never an orphan, Constitution V.4)

# Generated (rerun, never hand-edit)
.apm/skills/…            # generate_skill_mirror.sh
docs/COMMANDS.md         # generate_commands_doc.py (--check gates CI)
configs/gemini/GEMINI.md, AGENTS.md   # generate_commands_doc.py --inject-guides
configs/cursor/rules/…   # generate_cursor_rules.sh (+ verify generate_cursor_agents.py / generate_cursor_mcp.py output unchanged or intentionally extended)

# Tests
tests/python/test_delegate_dispatcher.py   # config precedence, envelope, registry, fault matrix (SC-004)
tests/python/test_delegate_jobs.py         # job lifecycle: bg spawn/status/result/cancel/timeout, keep-last-50
tests/bats/delegate_plugin.bats            # registration gates, --help, hook wiring, registry↔cli_agents drift
```

**Structure Decision**: Single self-contained plugin bundle (SC-005 forbids
depending on deployed `~/.claude/scripts/`), plus the six mandatory
registration surfaces and generator reruns that every bundle addition
requires (SKILL-NAMING.md lifecycle). Skills — not baseline-style `commands/`
— because the repo's budget/naming/doc/test apparatus covers skills only
(research.md D6). Job verbs are dispatcher subcommands surfaced through the
`delegate` skill, keeping the frontmatter surface at 2 descriptions.

## Delegation & job-management design (decision summary)

Authoritative detail in research.md; load-bearing points:

- **Mechanism (D1)**: one-shot CLI executions + per-job record dirs; background
  = a detached plugin worker supervising the backend's process group (owns
  the budget timeout + pgid kill, writes the envelope atomically, sets the
  terminal state exactly once); cancel = pgid kill + compare-and-replace
  cancellation of non-terminal records only (terminal ⇒ reported no-op —
  completion and cancel cannot race); resume = stored backend session/thread
  id replayed through each CLI's native resume. The baseline's persistent app-server broker is
  deliberately not reproduced — it is codex-only machinery, and FR-014/FR-015
  demand the capability, not the mechanism.
- **Observability (D2)**: `record.json` + `output.txt` + `job.log` per job,
  keep-last-50 per workspace under `~/.claude/.agent_outputs/delegations/`.
- **Standalone review parity**: the `review` subcommand (with `--adversarial`
  + free-text focus) generalizes baseline `/codex:review` and
  `/codex:adversarial-review` across all backends, fg/bg, always read-only —
  distinct from the finish-time gate (spec-review amendment 2026-08-05).
- **Review gate (D9)**: soft gate, off by default, fail-open; at-most-once
  enforced by the Stop payload's `stop_hook_active` re-entry indicator
  (gate-kind job records kept as audit trail); deterministic finishing-turn
  edit detection; block reason forbids tool use + requires asking the
  developer; 600s default budget capped at
  840s under the 900s hook timeout, never auto-applies.
- **Safety (D8)**: read-only default; `--write` pre-authorizes only
  sandbox-scoped workspace edits — approval-escalating/destructive actions
  stay denied in non-interactive mode. Concrete profiles: codex `--sandbox
  read-only|workspace-write`; claude sandbox-enabled `--settings` +
  read-only `--permission-mode plan` (write: `acceptEdits`) + constrained
  tools/dirs; agy `--sandbox --mode plan|accept-edits` — sandbox + explicit
  mode in BOTH modes. Bypass tokens
  (`dangerously|bypass`) are unrepresentable in the registry schema AND
  re-validated at dispatcher load (violating registry refuses to run);
  fault tests cover outside-workspace writes + destructive commands.
- **Model policy (FR-009/D3)**: economical tier defaults (codex `auto`, claude
  `sonnet`, agy `flash`); premium only on explicit request; tiers resolved by
  name via `model_tiers` when deployed config exists.

## Phase 2 → tasks.md expectations (for /speckit-tasks)

Task generation should follow story priority order: US1 delegation core
(registry + dispatcher `task`/`status`/`result`/`cancel` + skills + agent) →
US2 readiness (`setup`) → US3 second opinion (`task --second-opinion` reusing
US1 plumbing) → standalone `review`/`--adversarial` (SC-002 parity rows 3–4)
→ US4 gate (hooks) → supersession (MIGRATION.md + SC-002 traceability check)
→ registration/generators/tests/smoke. Implementation PR
carries the Principle II parallel-agent cross-verification gate.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| First plugin bundle shipping `hooks/` (new repo surface) | FR-006 finish-time gate parity requires a Stop hook; SessionEnd cleanup guarantees FR-012's no-orphan rule | Gate-as-skill (manual invocation) is not a completion-time gate; deployed-tree hooks would break marketplace-only install (SC-005) |
| New runtime state root (`.agent_outputs/delegations/`) | FR-014 background jobs must be inspectable across turns/harnesses | Reusing the baseline's `${CLAUDE_PLUGIN_DATA}/state` is Claude-session-scoped and unavailable to other harnesses; a shared index file reintroduces serialized shared writes |
