# Implementation Plan: Skill Naming Taxonomy

**Branch**: `480-skill-naming-taxonomy` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/480-skill-naming-taxonomy/spec.md`

## Summary

Migrate the 91-skill library to the ratified `<purpose>-<verb>[-<qualifier>]`
taxonomy: document the standard (`docs/SKILL-NAMING.md`) with an enforced bats
conformance gate, merge two duplicate clusters, delete deprecated `browser-test`,
apply the 68-entry ratified rename map via scripted `git mv` + frontmatter edits,
update every name-keyed registry and cross-reference, regenerate all derived
artifacts, and verify with the full gate chain. One PR, per-phase commits.

## Technical Context

**Language/Version**: Bash (bats-core tests), Python 3 (generators), YAML configs

**Primary Dependencies**: `generate_cursor_rules.sh`, `generate_commands_doc.py`
(regenerates `docs/COMMANDS.md` + guide sections in `configs/gemini/GEMINI.md` and
`AGENTS.md`), `command_catalog.py`, pre-commit chain, bats + pytest suites

**Storage**: N/A (filesystem renames + text edits)

**Testing**: `bats tests/bats/`, `pytest tests/python/`, pre-commit `--from-ref origin/main`

**Target Platform**: repo CI (GitHub Actions) + deployed assistant homes via bootstrap

**Project Type**: configuration/tooling monorepo

**Constraints**: `subagent_policy.bats` enforces 1:1 skills↔`tool_policies`;
`context_budget.bats` enforces auto-loaded description budget; CI drift checks fail on
stale `docs/COMMANDS.md` or `configs/cursor/rules/*.mdc`; eof-fixer vs cursor-rules
double-newline conflict (regen then run real pre-commit)

**Scale/Scope**: 68 dir renames, 2 merges, 1 deletion; ~7 name-keyed YAML registries;
~140 generated files touched; curated tables in 6+ docs; hardcoded names in tests

## Constitution Check

- State-gated lifecycle: specify ✅ (committed) → plan (this doc) → tasks → implement →
  verify. No user-facing runtime workflow is added; the shipped "workflow" is the
  conformance gate itself, smoke-covered by the new bats test executing against the real
  library (Verify gate). Review gates: spec checklist passed; PR review is the human gate.
- No security-sensitive surface; no new dependencies; no schema changes.

## Project Structure

### Documentation (this feature)

```text
specs/480-skill-naming-taxonomy/
├── spec.md              # ratified convention, map, exceptions
├── plan.md              # this file
├── checklists/requirements.md
├── rename-map.tsv       # machine-readable ratified map (drives migration + closeout)
└── tasks.md
```

### Source Code (repository root)

```text
.skillshare/skills/<name>/SKILL.md      # renamed dirs + frontmatter (source of truth)
docs/SKILL-NAMING.md                    # NEW: convention, vocabulary, exceptions
tests/bats/skill_naming.bats            # NEW: conformance gate
configs/claude/config/command_config.yml        # tool_policies keys (1:1)
configs/claude/config/command_categories.yml    # category membership
configs/claude/config/validation_criteria.yml   # command_overrides keys
configs/claude/config/hint_registry.yml         # command_refs + refactor-* trigger
configs/claude/config/knowledge_base.yml        # skill references in learnings
configs/claude/config/language_profiles.yml     # refactor skill references
configs/claude/config/lifecycle_providers.yml   # lifecycle/speckit skill references
.specify/extensions.yml                 # after_implement hook: speckit-implement-review
configs/cursor/rules/*.mdc              # regenerated; old-name files DELETED
docs/COMMANDS.md, configs/gemini/GEMINI.md, AGENTS.md   # regenerated sections
README.md, CLAUDE.md, .claude/CLAUDE.md, configs/claude/CLAUDE.md  # curated tables
tests/bats/*.bats, tests/python/**      # hardcoded names updated
```

## Execution Design

### Phase order (one commit each)

1. **Standard + gate**: `docs/SKILL-NAMING.md` (pattern, domain vocabulary, verb
   guidance, exceptions + rationale, new-domain process) and
   `tests/bats/skill_naming.bats` validating every `.skillshare/skills/*/`:
   (a) name matches `^<domain>(-<token>){1,3}$` with first token(s) in the vocabulary,
   (b) name in exception list bypasses (a), (c) frontmatter `name:` == dir name.
   Vocabulary lives in a machine-readable block inside `docs/SKILL-NAMING.md` parsed by
   the test (single source of truth, no second registry file).
2. **Merges + deletion**: write merged `memory-compress` and `pr-triage-bots`
   SKILL.md (union of guidance; keep the richer body as base, fold in the other's
   unique triggers/steps), `git rm` the four predecessors + `browser-test`; update all
   references to these five names in the same commit.
3. **Renames**: scripted loop over `specs/480-skill-naming-taxonomy/rename-map.tsv`:
   `git mv .skillshare/skills/<old> .skillshare/skills/<new>` + in-place frontmatter
   `name:` edit. No other content edits in this commit (clean rename detection).
4. **Registry + reference sweep**: update name-keyed YAML registries, extension hook
   wiring, curated doc tables, cross-skill `/old-name` mentions, and hardcoded test
   names. Long hyphenated names: global word-boundary replace. Generic single-word
   names (`verify`, `checkpoint`, `dashboard`, `lifecycle`, `scaffold`) are replaced
   ONLY in exact-token contexts (slash-invocation `/name`, YAML keys, quoted list
   entries) with per-hit manual review — never blind sed.
5. **Regeneration**: delete stale old-name `configs/cursor/rules/<old>.mdc`, run
   `generate_cursor_rules.sh`, run `generate_commands_doc.py` (COMMANDS.md + GEMINI +
   AGENTS), re-measure `context_budget.bats` headroom and fix its comment.
6. **Verify + fix**: `pre-commit run --from-ref origin/main --to-ref HEAD`,
   `bats tests/bats/`, `pytest tests/python/`, zero-stale-name sweep script
   (grep for all 71 retired names outside allowed files).

### Risk register

- **Generic-word renames** (`verify` et al.): mitigated by context-scoped replacement +
  manual diff review of every hit (design above).
- **`refactor-*` hint trigger glob** breaks post-rename → update to explicit new-name
  refs or a `*-refactor` glob if the hint engine supports suffix globs (check
  `guidance_hint.py`; else enumerate).
- **1:1 policy test** fails between commits 3 and 4 — acceptable; gates run on the PR
  head, and each commit is still reviewable.
- **eof-fixer vs .mdc double-newline**: run the real pre-commit chain after regen
  (memory: cursor-rules-eof-fixer-conflict); `.mdc` dir exclusion already configured.
- **Deployed homes**: out of this PR (runtime); post-merge `./bootstrap.sh` +
  `/deploy-reconcile` preview is recorded in the issue closeout as the user's step —
  `.deployed-skills` manifest prune behavior verified in #457.
- **skillshare tracking**: `ai-hooks-integration` untouched (exception);
  `.skillshare/.gitignore` re-checked after any skillshare-touching change.

## Complexity Tracking

No constitution deviations. Single-PR delivery deviation from the issue's suggested
phased-PR sequence is ratified in the spec (decision 7).
