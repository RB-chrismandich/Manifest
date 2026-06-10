# Tasks: Skill Library Consolidation & Repo Health Hardening

**Input**: Design documents from `/specs/003-skill-library-consolidation/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec mandates test coverage (FR-005a prune test, FR-011 guard self-test, FR-013 suites) and the constitution requires bats/pytest green per PR.

**Organization**: One phase per user story; each story ships as its own PR (research R14), independently CI-green. PR-gate: US1 and US3 always require parallel-agent cross-verification (skill-content rewrite >200 lines; security-adjacent quoting); US2/US4/US5 require it whenever their diff exceeds 200 lines (Constitution II — gates embedded in T021/T035/T040).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 per spec.md

## Phase 1: Setup

**Purpose**: Confirm a green baseline so every story-PR diff is attributable.

- [ ] T001 Verify baseline: run `bats tests/bats/ && python3 -m pytest tests/python/ -q && shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh` from repo root; record pass in PR-1 description

---

## Phase 2: Foundational

**Purpose**: None required — the five stories share no blocking prerequisites (existing repo infrastructure suffices). Intentionally empty.

---

## Phase 3: User Story 1 — Skill library consolidation (P1) → PR-1

**Goal**: 6 clusters → 7 survivors (81 → 69 skills), deletions propagate to deploy targets, evolve stops re-proposing duplicates.

**Independent test** (quickstart.md §US1): skill count 69±1; deleted names absent and unreferenced; `bats tests/bats/deploy_skills.bats` and evolve pytest green.

### Tests first (pin new behavior)

- [ ] T002 [P] [US1] Add prune-on-deploy bats cases to tests/bats/deploy_skills.bats per contracts/prune-on-deploy.md: (a) deploy → remove skill from source → redeploy → gone from target, (b) file outside skills dir survives, (c) double-deploy is a no-op — expect FAIL until T003
- [ ] T003 [US1] Add `--delete` to the `rsync -a` in `deploy_home_skills()` in bootstrap/lib/common.sh (R1); T002 now passes
- [ ] T004 [P] [US1] Add library-prompt pytest cases to tests/python/test_skillclaw_evolve.py per contracts/library-prompt.md: name—description line present; broken-frontmatter → name-only (run succeeds); >200-char description truncated — expect FAIL until T005
- [ ] T005 [US1] Implement description-aware library rendering in configs/claude/scripts/skillclaw_evolve.py (extend `_library_names` → `_library_entries`, flatten/truncate at 200 chars, fail-open per contract); T004 now passes
- [ ] T006 [US1] Update library-section wording in configs/claude/prompts/skillclaw_evolve.md: "do NOT duplicate these skills — match by purpose, not just name; improvements go under the EXISTING name" (contracts/library-prompt.md rule 5)

### Cluster merges (each [P] — disjoint file sets; follow contracts/merged-skill.md)

- [ ] T007 [P] [US1] Merge PR-comments cluster: rewrite .skillshare/skills/address-pr-comments/SKILL.md to absorb address-pr-review-comments + address-review-comments (description covers inline comments, review bodies, issue-level discussion; `> Absorbed:` footer); `git rm -r` the two absorbed dirs
- [ ] T008 [P] [US1] Merge session-memory cluster: fold any distinct content from session-memory-digest into .skillshare/skills/session-memory-compress/SKILL.md (both modes); `git rm -r` .skillshare/skills/session-memory-digest
- [ ] T009 [P] [US1] Merge live-data cluster: rewrite .skillshare/skills/live-data-validation/SKILL.md with Smoke / Before-merge / After-green-tests subsections absorbing live-data-validation-before-merge, live-data-smoke-validation, real-data-validation-after-green-tests; `git rm -r` the three absorbed dirs
- [ ] T010 [P] [US1] Create .skillshare/skills/verify-premise/SKILL.md with CLI-binary / API-schema / image-runtime subsections absorbing verify-cli-premise, verify-cli-premise-before-tooling, verify-tool-premise, verify-api-schema-before-trust, verify-image-runtime-contract; `git rm -r` the five absorbed dirs
- [ ] T011 [P] [US1] Create .skillshare/skills/retire-component-cleanup/SKILL.md with daemon / tool-runtime / plugin-MCP subsections absorbing daemon-migration-verification, retire-migrated-tool-runtime, plugin-mcp-clean-removal; `git rm -r` the three absorbed dirs
- [ ] T012 [P] [US1] Add mutual decision-anchor lines to .skillshare/skills/reset-reapply-clean-pr/SKILL.md and .skillshare/skills/clean-pr-from-stale-base/SKILL.md ("If <other root cause>, use <other> instead")

### Story verification & PR

- [ ] T013 [US1] Repo-wide reference sweep for all 12 deleted names (quickstart.md §US1 loop); fix any hits outside specs/003-* and CHANGELOG; confirm skill count = 69
- [ ] T014 [US1] Run quickstart.md §US1 + full gate (pre-commit, bats, pytest); regenerate cursor rules (`configs/claude/scripts/generate_cursor_rules.sh`) since skill set changed; commit
- [ ] T015 [US1] Parallel-agent cross-verification of the consolidation diff (Constitution II — >200 lines of skill content): `~/.claude/scripts/parallel_agent.py --json --timeout 600 --review` on the changed SKILL.md files; address findings; open PR-1 with content-preservation table (per-cluster: variant → where its content landed) and the R1 directory-scope pruning interpretation for reviewer sign-off

**Checkpoint**: PR-1 merged → library consolidated, pruning live, evolve dedup-hardened. MVP complete.

---

## Phase 4: User Story 2 — Documentation accuracy (P2) → PR-2

**Goal**: counts/tables/changelog/stamps truthful; spec-systems map exists.

**Independent test** (quickstart.md §US2): no "28 skills" hits; tables consistent; Unreleased clean; SPEC-SYSTEMS.md exists; cursor-rules drift check green.

- [ ] T016 [US2] Update docs/COMMANDS.md as canonical: verify every row against `.skillshare/skills/*/SKILL.md` frontmatter and configs/claude/config/command_config.yml (post-US1 skill set), fix wording/flags (R6 note: /version-pin wording per docs/COMMANDS.md style)
- [ ] T017 [US2] Unify the three mirror tables to match T016 exactly: root CLAUDE.md, AGENTS.md, configs/claude/CLAUDE.md; refresh their "Last Updated" stamps to change date; fix skill counts in AGENTS.md:207 and README.md (use `find .skillshare/skills -name SKILL.md | wc -l` result)
- [ ] T018 [P] [US2] CHANGELOG.md: move shipped Unreleased items (promote audit log etc.) into a dated `[2026-06]` section; add entries for this feature's PRs as they land
- [ ] T019 [P] [US2] Prepend archive banner to docs/SHELL_ANALYSIS_REPORT.md: `> [ARCHIVED 2026-06-10] Analyzes the retired parallel_agent.sh; superseded — see configs/claude/scripts/ for current tooling`
- [ ] T020 [P] [US2] Create docs/SPEC-SYSTEMS.md per research R9 (roles of specs/+.specify/, docs/superpowers/, configs/claude/.plans/, .Jules/); link it from README.md, docs/README.md, and .claude/CLAUDE.md
- [ ] T021 [US2] Run quickstart.md §US2 + full gate; markdownlint clean; if the diff exceeds 200 lines (likely), run parallel-agent cross-verification (`~/.claude/scripts/parallel_agent.py --json --timeout 600 --review` on changed files) per Constitution II before opening PR-2

**Checkpoint**: docs match reality; drift map published.

---

## Phase 5: User Story 3 — Script robustness (P3) → PR-3

**Goal**: no interpreter-source interpolation, bounded evolve, guarded array class, no deployed test files.

**Independent test** (quickstart.md §US3): quote-path parse succeeds; timeout pytest green; guard clean at HEAD and catches a planted violation; no test_*.py under configs/claude/scripts/.

- [ ] T022 [P] [US3] Fix parse_labels in configs/claude/scripts/label_sync.sh:112-121 — pass `$file` as `sys.argv[1]`; add a bats case to tests/bats/label_sync.bats parsing a labels.yml under a path containing a single quote
- [ ] T023 [P] [US3] Fix configs/claude/scripts/browser_test.sh lines ~174/~182 (`open('$file')`) and ~186 (`$DEFAULT_MAX_STEPS`) — argv passing for all three (R5)
- [ ] T024 [P] [US3] Add timeout pytest to tests/python/test_skillclaw_evolve.py (runner raising subprocess.TimeoutExpired → chunk fails as RuntimeError, run continues per fail-continue) then implement `--chunk-timeout`/`SKILLCLAW_CHUNK_TIMEOUT` (default 600) on subprocess.run in configs/claude/scripts/skillclaw_evolve.py:111 (R3)
- [ ] T025 [US3] Write tests/lint/check_array_expansion.sh per contracts/array-guard.md (detection rule, `# array-safe` opt-out, exit 0/1, findings as `file:line: name`); include fixture self-test proving a planted violation is caught
- [ ] T026 [US3] Sweep all tracked *.sh for unsafe empty-array expansions; convert to `${arr[@]+"${arr[@]}"}` or annotate `# array-safe`; guard exits 0 at HEAD
- [ ] T027 [US3] Wire the guard both places (clarification): local repo hook in .pre-commit-config.yaml + step in the lint job of .github/workflows/ci.yml
- [ ] T028 [P] [US3] `git mv configs/claude/scripts/test_oauth.py configs/claude/scripts/test_parallel_agent.py tests/python/`; fix their sys.path inserts for the new location; `grep -rn "scripts/test_oauth\|scripts/test_parallel_agent"` → fix any references; pytest green
- [ ] T029 [US3] Run quickstart.md §US3 + full gate; parallel-agent cross-verification (Constitution II — security-adjacent quoting changes); open PR-3

**Checkpoint**: robustness class bugs closed and guarded.

---

## Phase 6: User Story 4 — Test & CI gaps (P4) → PR-4

**Goal**: highest-risk untested scripts covered; CI pinned + cached.

**Independent test** (quickstart.md §US4): three new bats suites green locally and in CI; pins present; cache hit on second CI run.

- [ ] T030 [P] [US4] Create tests/bats/learning_capture.bats: ≥1 behavioral test per subcommand (add, query, stats, increment, sync-docs) + missing-knowledge_base.yml error path (sandbox HOME, fixture YAML) — NOT descopeable per spec
- [ ] T031 [P] [US4] Create tests/bats/check_status.bats: services.yml parsing, enabled-flag detection, MANIFEST_STATE_ROOT resolution, output shape
- [ ] T032 [P] [US4] Create tests/bats/generate_cursor_rules.bats: rule count matches skill count, skill→rule mapping, empty-skills-dir handling
- [ ] T033 [US4] Pin CI tool versions in .github/workflows/ci.yml to match .pre-commit-config.yaml (yamllint==1.35.1, bats npm pin, shellcheck pinned action/version) (R13)
- [ ] T034 [US4] Add dependency caching to .github/workflows/ci.yml: actions/setup-python `cache: pip` + npm cache for bats, cache keys including the pin strings (spec edge case: pin bump invalidates)
- [ ] T035 [US4] Run quickstart.md §US4 + full gate; compare CI wall-time before/after (target ≥20s median, SC-008); if the diff exceeds 200 lines (likely — three new suites), run parallel-agent cross-verification per Constitution II; open PR-4
- [ ] T035a [US4] Record the browser_test.sh coverage decision: per spec assumption it is reviewer-descopeable — either add a minimal tests/bats/browser_test.bats (subcommand routing + missing-browser-use exit path only) or document the descope rationale in PR-4's description (decision must be explicit, not silent)

**Checkpoint**: untested-surface risk retired; CI reproducible and faster.

---

## Phase 7: User Story 5 — Repository hygiene (P5) → PR-5

**Goal**: clean status, archived delivered work, consistent conventions.

**Independent test** (quickstart.md §US5): records/ ignored; no stale current-plan pointer; --help present on the 8 user-facing scripts.

- [ ] T036 [P] [US5] Add `records/` to .gitignore with comment `# local tool side-effect, origin unknown (not SkillClaw — see specs/003 research R10)`
- [ ] T037 [P] [US5] Review specs/002-new-agent-skills/ deliverables (R11); if delivered mark plan.md/spec.md status "Delivered 2026-06"; confirm root CLAUDE.md SPECKIT pointer already repointed to 003 (done in planning) and remove any other stale "current plan" references
- [ ] T038 [US5] err() convention sweep in configs/claude/scripts/*.sh: convert bare `echo ... >&2` / print_error uses to `err()` (bootstrap/lib/ exempt per clarification); document the convention + exemption in .claude/CLAUDE.md
- [ ] T039 [US5] Add minimal `--help` (usage + flags, ≤15 lines) to the 8 user-facing scripts lacking it: branch_clean.sh, check_status.sh, git_ops.sh, linear_ops.sh, pr_review.sh, skillclaw_promote.sh, sync-skills.sh, version_pin.sh; document exemptions (version_pin_hook.sh, git_platform.sh) in .claude/CLAUDE.md (R6)
- [ ] T040 [US5] Run quickstart.md §US5 + full gate; if the diff exceeds 200 lines (likely — 10-script sweep), run parallel-agent cross-verification per Constitution II; open PR-5

**Checkpoint**: hygiene complete.

---

## Phase 8: Polish & Cross-Cutting

- [ ] T041 Confirm SC-001…SC-004, SC-006…SC-009 evidence across merged PRs (quickstart full-gate outputs in each PR description); note SC-005 (next evolve cycle proposes zero duplicates) as a post-merge observation with owner follow-up
- [ ] T042 [P] Tick specs/003-skill-library-consolidation/checklists/requirements.md items still open; update CHANGELOG.md with the feature summary; consider `/speckit-analyze` for final cross-artifact consistency

---

## Dependencies & Execution Order

```text
Phase 1 (T001) ──► US1 (T002–T015) ──► US2 (T016–T021) ─┐
                                                         ├─► Polish (T041–T042)
                   US3 (T022–T029) ──► US4 (T030–T035) ─┤
                   US5 (T036–T040) ─────────────────────┘
```

- **US1 → US2 ordering matters**: US2's tables/counts must reflect the post-consolidation skill set (T016/T017 depend on T007–T013).
- **US3, US5 are independent** of US1/US2 and of each other (disjoint files except .claude/CLAUDE.md in T038/T039 — same story, sequential anyway).
- **US4 after US3** only because T033/T034 and T027 both edit ci.yml (merge-conflict avoidance, not a logical dependency).
- Within US1: T002→T003, T004→T005 (test-first pairs); T007–T012 fully parallel; T013 after all merges; T014→T015 last.

## Parallel Execution Examples

- **US1 merges**: T007, T008, T009, T010, T011, T012 — six disjoint skill-file sets, one subagent each.
- **US1 infra**: T002+T003 (deploy) ∥ T004+T005+T006 (evolve) ∥ the merge block above.
- **US3**: T022 ∥ T023 ∥ T024 ∥ T028 (different files); T025→T026→T027 sequential (guard then sweep then wiring).
- **US4**: T030 ∥ T031 ∥ T032 (three new suites).
- **Cross-story**: US3 and US5 can run concurrently with US1 on separate branches.

## Implementation Strategy

**MVP = US1 (PR-1)**: the consolidation alone delivers the headline value (better triggering, less context, deletions propagated, dupes suppressed at source). Ship it first, alone.

Then incremental: PR-2 (docs reflect new reality) → PR-3/PR-5 (parallelizable) → PR-4 → Polish. Each PR independently CI-green; US1 and US3 PRs carry the Constitution II parallel-agent cross-verification note in their descriptions.

**Total**: 43 tasks (US1: 14, US2: 6, US3: 8, US4: 7, US5: 5, Setup/Polish: 3).
