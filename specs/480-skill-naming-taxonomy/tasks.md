# Tasks: Skill Naming Taxonomy

**Input**: Design documents from `/specs/480-skill-naming-taxonomy/`

**Prerequisites**: plan.md, spec.md (ratified map in `rename-map.tsv`)

**Tests**: The conformance gate (T003) is the feature's Verify-gate smoke test — it
executes against the real migrated library. Remaining tasks are migration mechanics,
exempt from per-task smoke tests (no new user-facing runtime workflow).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Standard + Gate (US1)

- [x] T001 [US1] Author `docs/SKILL-NAMING.md`: pattern, machine-readable domain
      vocabulary block, verb guidance, qualifier rules, exception list
      (`help`, `pass-cli`, `graphify`, `ai-hooks-integration`) with rationale,
      new-domain process.
- [x] T002 [US1] Ship ratified `specs/480-skill-naming-taxonomy/rename-map.tsv`
      (68 entries) as the machine-readable migration driver.
- [x] T003 [US1] Add `tests/bats/skill_naming.bats`: every skill dir name conforms
      (vocabulary-checked first token, 2–4 tokens) or is excepted; frontmatter
      `name:` == dir name; actionable failure message.

## Phase 2: Merges + Deletion (US2)

- [x] T004 [US2] Merge `memory-log-compress` + `session-memory-compress` →
      `.retired skill supply/skills/memory-compress/SKILL.md` (union of triggers/guidance);
      `git rm` predecessors.
- [x] T005 [US2] Merge `bot-pr-triage` + `triage-bot-pr-flood` →
      `.retired skill supply/skills/pr-triage-bots/SKILL.md` (union); `git rm` predecessors.
- [x] T006 [US2] Delete `.retired skill supply/skills/browser-test/` and every reference to it.
- [x] T007 [US2] Update all references to the four merged-away names to the two
      successors (configs, docs, tests, skill bodies).

## Phase 3: Renames (US3)

- [x] T008 [US3] Scripted migration from `rename-map.tsv`: `git mv` each dir +
      frontmatter `name:` edit; no other content changes in the commit.

## Phase 4: Registries + References (US3)

- [x] T009 [US3] Update name-keyed registries 1:1: `command_config.yml`
      `tool_policies`, `command_categories.yml`, `validation_criteria.yml`
      `command_overrides`, `hint_registry.yml` (incl. `refactor-*` trigger),
      `knowledge_base.yml`, `language_profiles.yml`, `lifecycle_providers.yml`.
- [x] T010 [US3] Update `.specify/extensions.yml` hook wiring
      (`speckit-implement-review` → `speckit-audit-tasks`) and any skill-name refs in
      `configs/claude/scripts/` + bootstrap libs.
- [x] T011 [US3] Sweep cross-skill `/old-name` mentions in all SKILL.md bodies and
      skill scripts.
- [x] T012 [US3] Update curated doc tables: README.md, CLAUDE.md, .claude/CLAUDE.md,
      configs/claude/CLAUDE.md, configs/gemini/GEMINI.md (curated parts), AGENTS.md,
      docs/* (COMMANDS.md handled by regen).
- [x] T013 [US3] Update hardcoded names in `tests/bats/*.bats` and `tests/python/**`.
      Generic-word names (`verify`, `checkpoint`, `dashboard`, `lifecycle`,
      `scaffold`) only in exact-token contexts with per-hit review.

## Phase 5: Regeneration (US3)

- [x] T014 [US3] Delete stale `configs/cursor/rules/<old>.mdc` for all retired names;
      run `configs/claude/scripts/generate_cursor_rules.sh`.
- [x] T015 [US3] Run `configs/claude/scripts/generate_commands_doc.py`
      (docs/COMMANDS.md + GEMINI.md + AGENTS.md guide sections).
- [x] T016 [US3] Re-measure `context_budget.bats` totals; adjust headroom + comment.

## Phase 6: Verification (US1+US3)

- [x] T017 Zero-stale-name sweep: grep all 71 retired names repo-wide; allowed hits
      only in specs/480*, changelog/release notes, and .git history.
- [x] T018 `pre-commit run --from-ref origin/main --to-ref HEAD`, `bats tests/bats/`,
      `pytest tests/python/` all green.
- [x] T019 Push branch, open PR (old→new mapping table in body), post audit +
      closeout comment on issue #478.
