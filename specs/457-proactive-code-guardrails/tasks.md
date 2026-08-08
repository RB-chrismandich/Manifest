# Tasks: Proactive Code Guardrails

**Input**: Design documents from `/specs/457-proactive-code-guardrails/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the spec/constitution demands them — registry invariants and capture round-trips are bats-tested; each shipped user-facing workflow carries a smoke task (constitution Principle VI Verify gate). No speculative test tasks beyond that.

**Organization**: Tasks grouped by user story. US1 = write-time prevention (P1, MVP), US2 = audit skill (P2), US3 = learning loop (P3). The seeded registry is shared by all three stories → Foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3
- Exact file paths in every description

## Path Conventions

Configuration-toolkit repo (no `src/`): content lands in `configs/claude/`, `.retired skill supply/skills/`, `tests/bats/`, `tests/fixtures/` per plan.md Project Structure.

---

## Phase 1: Setup

**Purpose**: Baseline verification so later failures are attributable to this feature

- [X] T001 Record a green baseline: run `bats tests/bats/context_budget.bats tests/bats/learning_capture.bats tests/bats/commands_doc_drift.bats tests/bats/generate_cursor_rules.bats` and `yamllint configs/claude/config/knowledge_base.yml`; note current auto-loaded budget headroom (from context_budget.bats output) in the Notes section of specs/457-proactive-code-guardrails/checklists/requirements.md (same log T013/T019 use)
- [X] T002 [P] Re-read contracts before writing content: specs/457-proactive-code-guardrails/contracts/registry-schema.md and specs/457-proactive-code-guardrails/contracts/audit-skill-contract.md (schema invariants and report format are the acceptance targets for T004–T021)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The seeded registry — every user story reads it

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Update existing entries ANTI-001 and ANTI-002 in configs/claude/config/knowledge_base.yml in place with the new optional fields (`severity`, `detection_cue`, `prevention_rule`, `provenance: research-seed`) and one guardrail-category tag each (`security`), per contracts/registry-schema.md — do NOT create duplicate entries
- [X] T004 Seed configs/claude/config/knowledge_base.yml with the architectural (10), async-state (5), and error-handling (4) entries from research.md R7, continuing the ANTI-### ID sequence; each entry carries `prevention_rule`, `severity`, per-language `detection_cue` (bash/sh, python, javascript/typescript, go, terraform — where meaningful), `provenance: research-seed`, and exactly one guardrail-category tag
- [X] T005 Seed configs/claude/config/knowledge_base.yml with the remaining security (5 new; ANTI-001/002 updated in T003 complete the column), dependency (3), and iteration (4) entries from research.md R7, same field rules as T004; verify total guardrail-tagged entries ≥ 25 (expected: 33), all six category tags present, and all ten research-documented structural anti-patterns covered (FR-002)
- [X] T006 Create tests/bats/knowledge_base_registry.bats implementing the six invariants in contracts/registry-schema.md (severity enum, seeded entries have prevention_rule + exactly one category tag, all 6 categories covered, ≥25 guardrail entries, yamllint + safe_load pass); run it and make it green
- [X] T007 Run `configs/claude/scripts/learning_capture.sh sync-docs` against the seeded registry; if the generator chokes on or drops the new fields, extend its rendering minimally (show prevention_rule, summarize detection cues) and regenerate docs/KNOWLEDGE_BASE.md

**Checkpoint**: Registry seeded, schema-tested, docs regenerated — user stories can start (US1/US2/US3 are then independent)

---

## Phase 3: User Story 1 - Write-Time Anti-Pattern Prevention (Priority: P1) 🎯 MVP

**Goal**: Agents get prevention rules ambiently (guides) and as automated non-blocking advisory feedback (code-quality extension)

**Independent Test**: Give an agent the SC-003 spot-check task (async fetch helper with error handling) under deployed guidance; output must not swallow errors, skip boundary validation, or hardcode secrets. `bats tests/bats/context_budget.bats` still green.

- [X] T008 [P] [US1] Create configs/claude/references/antipatterns.md: full per-entry detail derived from the seeded registry (grouped by the six categories; each anti-pattern with description, per-language detection cues, prevention rule, severity), plus the iterative-refinement safety rule (FR-010) and the "user instruction wins, note the risk" conflict rule (spec Edge Cases)
- [X] T009 [US1] Add a compact Proactive Coding Guardrails digest (~15–20 lines: six categories + iron rules per research.md R4) to configs/claude/CLAUDE.md and register configs/claude/references/antipatterns.md in its Reference Index ("Read before writing/refactoring code"); keep additions inside the context budget
- [X] T010 [P] [US1] Mirror the digest into the non-Claude guides: configs/gemini/GEMINI.md, configs/codex/AGENTS.md target (root AGENTS.md), and configs/cursor/rules/orchestration.mdc — per repo token-economy rules these mirrors may carry slightly fuller text than the Claude guide (Antigravity needs no separate edit: it consumes the Claude guide via the existing configs/antigravity symlink chain)
- [X] T011 [US1] Extend .retired skill supply/skills/code-quality/SKILL.md with a "Registry anti-patterns (advisory)" section: on trigger, consult ~/.claude/config/knowledge_base.yml guardrail entries (including provenance: session-capture) and flag matches inline with the entry's prevention_rule; state explicitly that findings are non-blocking (FR-011) and blocking stays with Tier 1 gates
- [X] T012 [US1] Run `bats tests/bats/context_budget.bats`; if over budget, trim the T009 digest (never the reference doc) until green — raising the cap requires the justification pattern documented inside context_budget.bats and a note in plan.md Complexity Tracking
- [X] T013 [US1] Smoke (Verify gate): execute the SC-003 spot check from quickstart.md — request an async fetch helper + a secrets-touching config loader under the new guidance; record pass/fail per iron rule in specs/457-proactive-code-guardrails/checklists/requirements.md notes

**Checkpoint**: US1 alone is a shippable MVP (prevention guidance live everywhere, advisory checks active)

---

## Phase 4: User Story 2 - On-Demand AI-Code Audit (Priority: P2)

**Goal**: `/ai-code-audit` runs the seven ordered passes with evidence-traced, severity-classified, cross-verified findings

**Independent Test**: `/ai-code-audit tests/fixtures/audit-seeded` finds ≥90% of the 6 planted defects at correct severity, zero fabricated findings on clean files, verdict BLOCKED (planted critical credential), single invocation.

- [X] T014 [P] [US2] Create the seeded fixture tests/fixtures/audit-seeded/ (≤15 files, mixed TS + Python + shell): plant exactly one each of swallowed async error, hardcoded credential, dead module, single-implementation interface, missing listener teardown, unvalidated boundary input; include ≥4 clean files; add tests/fixtures/audit-seeded/README.md listing each plant with path:line (the answer key)
- [X] T015 [US2] Create .retired skill supply/skills/ai-code-audit/SKILL.md implementing contracts/audit-skill-contract.md: frontmatter name/description; invocation args (target-path, --passes, --since); the seven passes P0–P6 from data-model.md with per-pass evidence requirements; >50-file chunking by top-level directory with stated (never silent) chunking; P6 graceful skip on shallow history; registry-driven detection cues; the evidence rule (no path:line + trace → unverified observation only)
- [X] T016 [US2] Add the cross-verification protocol to .retired skill supply/skills/ai-code-audit/SKILL.md: every candidate critical/high finding is re-checked by one independent adversarial sub-agent instructed to refute from cited evidence (mirror the security-finding-refutation pattern); refuted → downgrade to unverified observation or drop (a status change, never a severity re-label); report marks cross-checked findings; include the report template and the severity→verdict mapping (critical→BLOCKED; high with Tier 1 tag security/error-handling→BLOCKED; other high→NEEDS_REVIEW; else APPROVED) verbatim from the contract
- [X] T017 [US2] Register ai-code-audit in configs/claude/config/command_config.yml under `tool_policies` (policy: conditional — sub-agent dispatch only for critical/high cross-verification) and under the appropriate group in configs/claude/config/command_categories.yml
- [X] T018 [US2] Run the derived-artifact regeneration chain for the new skill: configs/claude/scripts/generate_cursor_rules.sh, then `python3 configs/claude/scripts/generate_commands_doc.py` (docs/COMMANDS.md count/table); verify `bats tests/bats/generate_cursor_rules.bats tests/bats/commands_doc_drift.bats tests/bats/context_budget.bats` all green (new skill description counts against the budget)
- [X] T019 [US2] Smoke (Verify gate): run `/ai-code-audit tests/fixtures/audit-seeded` end-to-end; score against the T014 answer key (≥90% detection, correct severities, 0 fabricated findings, verdict BLOCKED); iterate on SKILL.md wording until pass criteria met; record the scored run in specs/457-proactive-code-guardrails/checklists/requirements.md notes

**Checkpoint**: Audit skill shipped and smoke-passed independently of US1/US3

---

## Phase 5: User Story 3 - Anti-Pattern Learning Loop (Priority: P3)

**Goal**: Confirmed anti-patterns captured in-session become active in guidance and audits with no restructuring (SC-005)

**Independent Test**: Capture a synthetic anti-pattern with the new fields via learning_capture.sh; verify it round-trips, renders in sync-docs, and is picked up by the code-quality and ai-code-audit consultation instructions (which read the live registry, not a snapshot).

- [X] T020 [US3] Extend configs/claude/scripts/learning_capture.sh to accept the four optional fields (severity, detection_cue, prevention_rule, provenance — flag or env interface, matching its existing argument style) and to accept a guardrail-category tag (via the existing tags mechanism if it already passes through, else a new flag) so captured entries satisfy the T006 invariants; invocation without them must remain byte-compatible with current behavior; route errors through the canonical `err()` helper and keep `--help` ≤15 lines
- [X] T021 [US3] Extend tests/bats/learning_capture.bats with round-trip cases: (a) entry written with all four new fields preserves them through capture and sync-docs, (b) legacy entry without new fields still succeeds, (c) invalid severity value is rejected with a non-zero exit; run `shellcheck configs/claude/scripts/learning_capture.sh` and make all green
- [X] T022 [P] [US3] Extend the capture flow of BOTH registry writers — .retired skill supply/skills/antipattern-detect/SKILL.md and .retired skill supply/skills/learning-loop/SKILL.md: when confirming a recurring anti-pattern, populate severity/detection_cue/prevention_rule and set `provenance: session-capture`; add the guardrail-category tag selection rule (exactly one of the six) to each
- [X] T023 [US3] Smoke (Verify gate): capture a synthetic `session-capture` entry via the extended learning_capture.sh, run sync-docs, confirm the entry appears in docs/KNOWLEDGE_BASE.md and satisfies knowledge_base_registry.bats invariants; then delete the synthetic entry and regenerate (leave no test residue)

**Checkpoint**: All three stories complete and independently verified

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T024 Full regeneration + real gate: re-run generate_cursor_rules.sh and generate_commands_doc.py, then `pre-commit run --from-ref origin/main --to-ref HEAD` (the changed-file gate that has bitten repo-wide sweeps before); fix anything it drags in
- [X] T025 Full test sweep: `bats tests/bats/` and `pytest tests/python/`; `shellcheck configs/claude/scripts/learning_capture.sh`; `yamllint configs/claude/config/*.yml`; `markdownlint` on new/changed markdown
- [X] T026 [P] Add a CHANGELOG entry for the feature per the repo's changelog convention (see recent `docs(changelog)` commits for format)
- [X] T027 Constitution Principle II gate: dispatch parallel-agent cross-verification of the full diff (security-relevant guidance + >200 lines) via `~/.claude/scripts/parallel_agent.py --json --timeout 600 --review` on the key changed files (absolute paths); attach the consensus verdict to the PR description; judge on completed agents only (known false-BLOCKED failure mode when an agent dies)
- [X] T028 Close the lifecycle advisory: run the spec-review panel via `~/.claude/scripts/spec_review.sh --spec specs/457-proactive-code-guardrails/spec.md --plan specs/457-proactive-code-guardrails/plan.md --tasks specs/457-proactive-code-guardrails/tasks.md` (the deployed script has no --mode flag; note the earlier lifecycle-phase override in the PR description); then `./bootstrap.sh` on the dev machine to deploy and re-run quickstart.md verification against the deployed home

---

## Dependencies & Execution Order

```text
Phase 1 (T001–T002)
   └─→ Phase 2 (T003 → T004 → T005 → T006 → T007)   # same file T003–T005: sequential
          ├─→ Phase 3 US1 (T008∥, T009 → T010∥, T011 → T012 → T013)
          ├─→ Phase 4 US2 (T014∥ ‖ T015 → T016 → T017 → T018 → T019)
          └─→ Phase 5 US3 (T020 → T021, T022∥ → T023)
                 └─→ Phase 6 (T024 → T025 → T026∥ → T027 → T028)
```

- **US1, US2, US3 are mutually independent** after Phase 2 — implement in priority order or in parallel work streams.
- Within US2, T014 (fixture) is parallel with T015–T016 (skill authoring); both must precede T019.
- T012/T018 both guard the same context budget — whichever story lands second re-runs the check.

## Parallel Execution Examples

- After T007: start T008 (reference doc), T014 (fixture), and T020 (capture script) simultaneously — three different files, three different stories.
- Within US1: T008 and T010 touch different guide files and can run in parallel once T009 defines the digest text.
- Polish: T026 (changelog) is parallel with T024/T025.

## Implementation Strategy

**MVP = Phase 1 + 2 + US1 (T001–T013)**: seeded registry + ambient prevention + advisory checks is already the "proactive" core the user asked for. Ship it, then add US2 (audit) and US3 (capture fields) as increments — each with its own smoke gate. Suggested single-PR delivery given shared regeneration chain, but the story checkpoints are valid stopping points if scope must cut.

**Format validation**: All 28 tasks follow `- [ ] T### [P?] [US?] description + explicit file path(s)`; story labels only in Phases 3–5. ✅
