# Phase 0 Research: Skill Library Consolidation & Repo Health Hardening

**Date**: 2026-06-10
**Spec**: [spec.md](spec.md)

All unknowns deferred from clarification are resolved below. Every decision is
grounded in verified repo state (file:line evidence gathered during planning).

## R1. Prune-on-deploy mechanism (FR-005a)

**Decision**: Add `--delete` to the `rsync -a` in `deploy_home_skills()`
(`bootstrap/lib/common.sh:140`), making bootstrap's home deploy a full mirror
of `.skillshare/skills/`.

**Rationale**: `sync-skills.sh:21-23` *already* mirrors with
`rsync -a --delete` to `~/.claude/skills` and all secondary targets — full
mirroring is the established semantic; bootstrap is the outlier. Constitution
Principle I (Configuration-as-Code) states deployed trees are tooling-owned and
manual edits to them are prohibited, so mirror semantics are constitutionally
correct.

**FR-005a safety bound interpretation**: "MUST NOT touch files the tooling did
not put there" is satisfied at *directory scope*: pruning applies only inside
the skills deploy directory (which both deployers fully own and one already
mirrors); no other part of `~/.claude` (or other targets) is touched. A
hand-added skill inside the skills dir is already deleted by any `sync-skills`
run today — this change makes bootstrap consistent with that existing,
constitution-aligned behavior. This interpretation is surfaced for reviewer
sign-off in the PR description.

**Test**: new bats case in `tests/bats/deploy_skills.bats` — deploy, remove a
skill from source, redeploy, assert it is gone from dest; plus a case asserting
files *outside* the skills dir are untouched.

**Alternatives considered**: manifest-based selective prune (track deployed
names in a state file; delete only previously-deployed names). Rejected:
more state to corrupt, diverges from sync-skills' existing semantic, and
protects a workflow (hand-editing deploy targets) the constitution prohibits.

## R2. Evolve library prompt: name + description (FR-005)

**Decision**: Extend `_library_names()` in `skillclaw_evolve.py:128-131` (or a
sibling `_library_entries()`) to parse each SKILL.md's `description:`
frontmatter and render `{{LIBRARY}}` as `- name — description` lines. Template
header (`configs/claude/prompts/skillclaw_evolve.md:9-11`) already says "do NOT
duplicate these names"; wording updates to "do NOT duplicate these skills
(match by purpose, not just name)".

**Rationale**: Names alone let the model re-propose the same workflow under a
new name (observed: `address-pr-review-comments` proposed alongside existing
`address-pr-comments`). Descriptions give it the semantic signal to match by
purpose.

**Alternatives considered**: embedding full SKILL.md bodies (token-expensive,
~80 × ~1KB against the chunk budget); post-hoc similarity filtering in
classify (heuristic, fights symptoms not cause). Description lines cost ~100
tokens/skill ≈ 7K total — acceptable within the 100K chunk budget.

## R3. Evolve per-chunk timeout (FR-010)

**Decision**: `subprocess.run(..., timeout=EVOLVE_CHUNK_TIMEOUT)` in
`skillclaw_evolve.py:111` with `DEFAULT_CHUNK_TIMEOUT = 600` (seconds),
overridable via `--chunk-timeout` and `SKILLCLAW_CHUNK_TIMEOUT`. On
`subprocess.TimeoutExpired`, raise the same `RuntimeError` shape the runner
already raises on non-zero exit, so the existing fail-continue path in
`skillclaw_promote.sh` ("evolve returned non-zero (continuing)") applies
unchanged.

**Rationale**: Observed real chunks complete in minutes; 600s is ~3-5× typical
worst case without letting a hang block a cron/long pipeline forever.

## R4. Empty-array guard (FR-011)

**Decision**: A small checker script (`tests/lint/check_array_expansion.sh` or
python) that flags `"${name[@]}"` / `"${name[*]}"` expansions in `.sh` files
where the array is not provably non-empty at that point, with an inline
opt-out comment (`# array-safe`) for false positives; wired as (a) a local
`repo` hook in `.pre-commit-config.yaml` and (b) invoked in the existing CI
lint job. Sweep + convert existing unsafe sites to `${arr[@]+"${arr[@]}"}`.

**Rationale**: shellcheck does not flag this (it's only a bug on Bash 3.2 +
`set -u`, which is exactly the macOS default this repo targets); two prior
production bugs (`team_args` in label_sync.sh, fixed 2026-06-10) prove the
class recurs. Clarification session fixed placement: both pre-commit and CI.

**Heuristic scope**: to avoid a research-grade static analyzer, the checker
flags expansions of arrays initialized as `=()` anywhere in the same file
unless the expansion uses the `+` guard or the line has the opt-out comment.
Accepted trade-off: a few opt-out comments in always-populated cases.

## R5. python3 -c interpolation fixes (FR-009)

**Decision**: Pass paths/values as argv: `python3 -c '...sys.argv[1]...' "$file"`.
Verified sites: `label_sync.sh:115` (`open('$file')`), `browser_test.sh:174`
and `:182` (`open('$file')`), `browser_test.sh:186` (`$DEFAULT_MAX_STEPS`
interpolated into Python int context — fix by passing as argv too).

**Rationale**: argv passing is the minimal, idiomatic fix; heredoc/stdin
alternatives complicate scripts that already read files in Python.

## R6. --help coverage reality check (FR-017)

**Finding (corrects the review)**: the end-to-end review claimed 3 scripts lack
`--help`; a full sweep found **10** `.sh` files in `configs/claude/scripts/`
without a `--help` handler: branch_clean, check_status, git_ops, git_platform,
linear_ops, pr_review, skillclaw_promote, sync-skills, version_pin,
version_pin_hook.

**Decision**: add a minimal `--help` (usage + flags, ≤15 lines) to the 8
user-facing entry points; exempt with documented rationale:
`version_pin_hook.sh` (save-hook wrapper, not user-invoked) and
`git_platform.sh` (internal detection helper sourced/called by git_ops).

## R7. Error-output convention sweep scope (FR-017)

**Decision** (clarified): `err()` (`scriptname: message` to stderr) is
canonical in `configs/claude/scripts/`; `bootstrap/lib/` keeps `print_error()`.
Implementation: convert bare `echo ... >&2` and any `print_error` usages inside
`configs/claude/scripts/` to `err()`; document the convention in
`.claude/CLAUDE.md` (developer guide).

## R8. Cluster inventory verification (FR-001)

All 19 cluster member directories verified present in `.skillshare/skills/`.
Deletion math: PR comments −2, session memory −1, live-data −3, premise
verification −4, component retirement −2 = **12 deletions**, 81 → **69**
skills. (Spec corrected from the review's "~14/67" estimate.)

Survivors and absorbed variants:

| Survivor | Absorbs |
|---|---|
| `address-pr-comments` | address-pr-review-comments, address-review-comments |
| `session-memory-compress` | session-memory-digest |
| `live-data-validation` | live-data-validation-before-merge, live-data-smoke-validation, real-data-validation-after-green-tests |
| `verify-premise` (new name; absorbs all 5 — see note) | verify-cli-premise, verify-cli-premise-before-tooling, verify-tool-premise, verify-api-schema-before-trust, verify-image-runtime-contract |
| `retire-component-cleanup` (new name) | daemon-migration-verification, retire-migrated-tool-runtime, plugin-mcp-clean-removal |
| `reset-reapply-clean-pr` + `clean-pr-from-stale-base` | (both kept; mutual decision-anchor lines added) |

Note: the premise-verification and component-retirement clusters get *new*
survivor names because no existing member's name covers the merged scope; this
counts as delete-5-add-1 and delete-3-add-1 respectively (net −4 and −2,
consistent with the math above).

## R9. Doc-map location (FR-008)

**Decision**: new `docs/SPEC-SYSTEMS.md` (linked from README.md, docs/README.md
and .claude/CLAUDE.md) mapping: `specs/` + `.specify/` = speckit feature flow;
`docs/superpowers/` = design-doc history (superpowers workflow);
`configs/claude/.plans/` = deployed plan-manage lifecycle; `.Jules/` = lesson
journal (linked, stays in place).

## R10. records/ origin (FR-015)

**Finding**: repo-wide grep for `records/`, `conversations.jsonl`,
`prm_scores.jsonl` finds **no producer** in this repo's scripts or skills —
not SkillClaw (its artifacts live under `~/.skillclaw/`). Created
2026-06-08 16:22 local, both files empty. Most likely an external/local tool
side-effect (name `prm_scores` suggests an eval/preference-model tool).

**Decision**: gitignore `records/`; note unknown origin in the change
description per spec. No deletion.

## R11. specs/002 status (FR-016)

**Decision**: verify `specs/002-new-agent-skills/` deliverables during
implementation (CHANGELOG 2026-05 suggests delivered); if confirmed, mark its
plan/spec status lines "Delivered", and repoint the root CLAUDE.md SPECKIT
block — which this feature's own Phase 1 already repoints to the 003 plan.

## R12. Misplaced test files (FR-012)

**Decision**: `git mv configs/claude/scripts/test_oauth.py tests/python/` and
`test_parallel_agent.py` likewise. Verify imports: both import the module
under test via path manipulation; update `sys.path` inserts to the new
relative location; confirm CI's pytest glob (`tests/python/`) picks them up
(it does — it runs the whole directory). Check nothing references their old
paths (`grep -r "scripts/test_oauth\|scripts/test_parallel_agent"`).

## R13. CI pinning + caching (FR-014)

**Decision**: pin in `.github/workflows/ci.yml`: shellcheck (apt version pin or
the `ludeeus/action-shellcheck` pinned action), `yamllint==1.35.1` (matches
pre-commit), `bats` npm version pin; add `actions/setup-python` `cache: pip`
keyed on the requirements/pin source, and `actions/cache` for the npm bats
install keyed on the pinned version string. Cache keys include the pin values
so bumps invalidate (spec edge case).

## R14. PR slicing

**Decision**: one PR per user story (5 PRs max, P1 first), each independently
CI-green — matches the spec's independent-testability framing and keeps the
skill-consolidation PR (the one needing closest human review) free of
unrelated diff noise.
