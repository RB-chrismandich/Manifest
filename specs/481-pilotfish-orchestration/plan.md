# Implementation Plan: Pilotfish-Style Cost-Tiered Model Orchestration

**Branch**: `481-pilotfish-orchestration` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/481-pilotfish-orchestration/spec.md`

## Summary

Vendor pilotfish's cost-tiered role-agent model into Manifest's deployed Claude config as an
opt-in, config-only integration. Add six role-agent Markdown files under
`configs/claude/agents/` (scout, Explore search-override, mech-executor, executor, verifier,
security-executor), each binding a role to a **built-in Claude Code model alias**
(`haiku`/`sonnet`/`opus` — not a custom name and not a raw model ID) plus a reasoning-effort
level; add a read-on-demand **delegation-policy reference** under `configs/claude/references/`
with a one-line pointer in the always-loaded `configs/claude/CLAUDE.md` Reference Index. Wire a
`--enable-pilotfish` / `--disable-pilotfish` bootstrap toggle (recorded in `services.yml`,
mirroring graphify/skillclaw), with an idempotent deploy step that (a) copies exactly the
pilotfish config when enabled, (b) removes exactly it when disabled via a **manifest-scoped
prune** (only the six role files + marker, preserving any coexisting user agent), and
(c) **aborts, touching nothing, when a non-Manifest-owned `~/.claude/agents/` already holds one
of the six pilotfish role-file names** (a differently-named user agent is not a collision; the
ownership marker makes an enabled re-run an idempotent no-op). The role files + delegation
reference are **excluded from the wholesale rsync** and deployed only by the gated step, so a
disabled or foreign home is never clobbered. Built-in aliases float to Manifest's current pins
(`opus`→Opus 4.8, `sonnet`→Sonnet 5, `haiku`→Haiku 4.5) with **no** deployed alias file and
**no** `settings.json` change (product spec-review correction — Claude Code does not resolve
custom frontmatter model names). The integration does **not** change the deployed main-session
model (FR-016), does **not** inline the policy into the budget-capped guide (FR-014), and ships
as a **distinct, complementary layer** beside subagent-driven-development and `parallel_agent.py`
(FR-015) — no refactor of either.

## Technical Context

**Language/Version**: Markdown (six agent files + policy reference), Bash (bootstrap deploy +
toggle wiring in `bootstrap/lib/`, bats tests), YAML (`services.yml` toggle state, agent
frontmatter). No new Python, no runtime code.

**Primary Dependencies**: `bootstrap.sh` + `bootstrap/lib/{config.sh,deploy.sh,common.sh}`
(toggle parse, `write_services_config()` heredoc, deploy/symlink chain), `services.yml`
(toggle store), `merge_claude_settings_defaults` (must remain **untouched** per FR-016),
`deploy_reconcile`/orphan-prune (scans only `skills`/`config` units — never `agents/` — so it
neither owns nor orphans the role files; R6),
`context_budget.bats` (budget gate on `configs/claude/CLAUDE.md`), `skill_naming.bats` /
naming taxonomy (agent filenames must not trip it), `generate_cursor_rules.sh` +
`generate_commands_doc.py` (derived-doc generators — verify agents/reference are out of their
scope so no derived drift).

**Storage**: `configs/claude/agents/*.md` (new dir; six role files — source of truth, deployed
to `~/.claude/agents/`), `configs/claude/references/pilotfish-delegation.md` (policy
reference, deployed to `~/.claude/references/`), one-line pointer in
`configs/claude/CLAUDE.md`, toggle flag in `services.yml`.

**Testing**: bats (`tests/bats/`) for: enable deploys exactly the six agents + reference;
disable removes exactly them and nothing else (clean add/remove, US3/SC-003);
collision-abort leaves the pre-existing file byte-identical (FR-008); toggle default is
disabled (opt-in); the deployed guide (source + injected pointer) stays under budget
(FR-009); reconcile/prune does not orphan `agents/`. Plus the existing gate suite
(shellcheck, yamllint, markdownlint, naming, derived-doc drift, `bootstrap_services.bats`).
**Principle VI Verify gate**: the critical-path enable→deploy→disable→collision→re-enable
workflow is verified by the **hermetic `deploy_pilotfish.bats` sandbox suite** (22 tests over a
temp HOME), which is the authoritative critical-path coverage for this config toggle. A live
smoke-catalog `cli` entry is deferred (T010) because it would only re-exercise the same gate
against the real `~/.claude` for no added signal; if wanted later, it must target a temp HOME.

**Target Platform**: Claude home only (`~/.claude/`); FR-013 excludes Cursor/Gemini/Codex/
Antigravity. macOS + Linux dev machines via the existing bootstrap deploy chain.

**Project Type**: Configuration/orchestration toolkit (this repo deploys agent config; no
application runtime). No `src/` tree.

**Performance Goals**: Enable + deploy adds no measurable bootstrap latency beyond copying
eight small Markdown files; session-start cost of the guide pointer is one line (FR-009).
Cost-reduction outcome (SC-001 ≥40%) is a property of the deployed policy at session runtime,
not of the deploy step.

**Constraints**: the **deployed** `~/.claude/CLAUDE.md` (committed source + injected pointer)
MUST stay under the `context_budget.bats` cap (FR-009) — full policy lives in the on-demand
reference, never the always-loaded guide (FR-014, token-economy rule); the verbose ALWAYS-list
was condensed to reclaim room. Deploy MUST be idempotent and toggle-gated (Principle V) —
idempotent because enable re-copies + re-injects and reconverges (the ownership marker
distinguishes owned from foreign). Collision handling is a fail-safe abort when a non-owned
agents dir already holds one of the six role-file names (FR-008 — a differently-named user agent
does not block enabling); the role files + reference are rsync-excluded and gate-deployed so a
disabled/foreign home is never clobbered; disable is a manifest-scoped prune that preserves
coexisting user agents (FR-006). Main-session model/settings untouched (FR-016). Security routing
is a control that MUST NOT be silently weakened (FR-004).

**Scale/Scope**: 6 agent files, 1 reference doc, 1 guide pointer line, 1 new bootstrap toggle
(+ services.yml key + deploy step), ~6–8 bats tests, 1 smoke-path addition, docs
(README/GETTING_STARTED toggle row, CONFIGURATION, plus MIT attribution + vendored-version
record per FR-011). Claude-only; no other assistant homes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Configuration-as-Code | PASS | All artifacts land in `configs/claude/{agents,references}/`, `configs/claude/CLAUDE.md`, `bootstrap/lib/`, and `services.yml` generation; deployed reproducibly by `bootstrap.sh`. No manual home-dir edits. |
| II. Parallel Agent Orchestration | PASS | The PR touches security-sensitive routing (FR-004) and will exceed 200 lines → parallel-agent cross-verification required before merge (planned in tasks). |
| III. Consensus-Driven Decisions | PASS | No new consensus scheme; the feature is orthogonal to `parallel_agent.py` scoring (FR-015 keeps them distinct). |
| IV. Skill-First Extensibility | PASS (with rationale) | Role-agents are Claude Code **agent-definition config data**, not a behavior absorbed into `parallel_agent.py` or other core scripts (which are untouched). No new capability skill is added in this feature (Option 1, not the Option-3 management skill). |
| V. Bootstrap Reproducibility | PASS | New deploy step is idempotent and existence-guarded; toggle default disabled; disable fully reverses (SC-003). Non-idempotent risk (collision) is a guarded hard-abort, not a degraded continue (FR-008, Principle V exit-non-zero posture). |
| VI. State-Gated Lifecycle | PASS (remediated 2026-07-09) | Phase 3 Spec-Review (product) initially skipped; **now run** — the parallel-agent panel returned 1 CONFIRMED finding (custom tier-aliases had no runtime resolution path), fixed across all artifacts (roles bind to built-in `haiku`/`sonnet`/`opus` aliases; no settings change), and re-review returned "✓ No inconsistencies found" (APPROVED). Verify gate: enable/deploy/disable is a shipped user-facing workflow → critical-path smoke coverage planned (see Testing). |

**Post-design re-check (after Phase 1)**: PASS — design artifacts add no new project, no
core-script expansion, no non-additive schema change, and no main-session settings mutation.
Principle VI is satisfied: `/spec-review --mode product` ran and returned APPROVED after the
one CONFIRMED finding was fixed.

## Project Structure

### Documentation (this feature)

```text
specs/481-pilotfish-orchestration/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (config entities: role agent, model alias, policy, toggle)
├── quickstart.md        # Phase 1 output (enable → verify → disable walkthrough)
├── contracts/
│   ├── agent-frontmatter.md   # role-agent file frontmatter + body contract
│   ├── delegation-policy.md   # policy-reference content contract (selective verify, escalation)
│   └── toggle-deploy.md       # --enable/--disable-pilotfish + services.yml + deploy/collision contract
├── checklists/requirements.md # (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source (repository) — files this feature adds or touches

```text
configs/claude/
├── agents/                          # NEW dir (source of truth → ~/.claude/agents/)
│   ├── scout.md                     # read-only lookup — model: haiku, low effort
│   ├── Explore.md                   # search override — model: haiku, low effort
│   ├── mech-executor.md             # fully-specified mechanical — model: sonnet, low effort
│   ├── executor.md                  # judgment work — model: opus, medium effort
│   ├── verifier.md                  # fresh-context CONFIRMED/REFUTED — model: opus, medium effort
│   └── security-executor.md         # security-sensitive — model: opus, high effort
├── references/
│   └── pilotfish-delegation.md      # NEW read-on-demand delegation policy (role→alias map, selective-verify)
└── CLAUDE.md                        # source stays pointer-free (verbose ALWAYS-list condensed for headroom); pointer injected into the DEPLOYED copy only
                                     # NOTE: agents/ is EXCLUDED from the wholesale rsync; the .pilotfish marker is WRITTEN by the gate, not shipped

bootstrap/lib/
├── config.sh                        # +--enable/--disable-pilotfish parse; services.yml key (write_services_config)
├── common.sh                        # +gate_pilotfish_agents() (gate-copies six from source/prune/marker/pointer) + check_pilotfish_collision() (six-name keyed) + inject/remove_pilotfish_pointer()
└── deploy.sh                        # +--exclude '/agents' on both rsyncs + pre-rsync collision guard + gate_pilotfish_agents "$TARGET_DIR" "$source_dir/agents" at both paths

tests/bats/
└── deploy_pilotfish.bats            # NEW: enable/disable/collision/budget/reconcile coverage

docs/                                # toggle row (README, GETTING_STARTED), CONFIGURATION, MIT attribution + vendored version
```

**Structure Decision**: No `src/` application tree — this is the Manifest config toolkit.
The feature's "code" is deployable Markdown config (`configs/claude/agents/`,
`configs/claude/references/`) plus Bash bootstrap wiring (`bootstrap/lib/`) and bats tests,
following the exact deploy/toggle pattern already used by graphify and skillclaw.

## Complexity Tracking

> No Constitution Check violations require justification. The single advisory (Principle VI,
> Spec-Review product not yet run) is logged above with a remediation recommendation, not a
> complexity violation.
