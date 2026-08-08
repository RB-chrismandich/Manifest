# Feature Specification: Skill Naming Taxonomy (`<purpose>-<verb>[-<qualifier>]`)

**Feature Branch**: `480-skill-naming-taxonomy`

**Created**: 2026-07-02

**Status**: Delivered (PR pending review)

**Input**: User description: "Adopt a `<purpose>-<verb>[-<qualifier>]` naming taxonomy across the skill library (issue #478): ratify the naming convention and domain vocabulary, merge duplicate skills first, delete deprecated browser-test, rename all non-conformant skills per the ratified map, document the convention and exception list in docs/SKILL-NAMING.md, and add a conformance lint/test so new skills must conform."

**Tracking issue**: [#478](https://github.com/RB-chrismandich/Manifest/issues/478)

## Fresh Inventory (2026-07-02 audit)

The library holds **91 skills** (the issue's 90-count sweep predates `antipattern-detect`,
added by spec 457 / PR #489, which is already conformant). Verified against the issue's
draft map: all 71 mapped "current" names still exist, zero proposed-target collisions
with existing directories, and every skill's frontmatter `name:` matches its directory.

Breakdown: 68 skills to rename (after ratification below), 2 duplicate pairs to merge
(4 skills → 2), 1 deprecated skill to delete (`browser-test`), 19 already-conformant
keepers, and 4 documented exceptions.

## Ratified Design Decisions

These settle the open questions the issue deferred to the spec phase:

1. **Convention**: `<purpose>-<verb>[-<qualifier>]` — purpose/domain token(s) first,
   action verb second, optional disambiguator last. 2–4 hyphenated tokens total.
   Multi-token purposes are allowed only when listed in the domain vocabulary
   (e.g. `ai-code`).
2. **Language-refactor altitude**: language-first, one altitude for all —
   `go-refactor`, `node-refactor`, `python-refactor`, `shell-refactor`,
   `terraform-refactor`. (Overrides the draft's `code-refactor-go`/`code-refactor-node`,
   which mixed altitudes with `python-refactor`.) Languages are purposes; this clusters
   each language's skills together (`shell-refactor` sorts beside `shell-audit-*`).
3. **Umbrella marker**: none. Umbrella (orchestrating) skills follow the same
   convention as leaf skills; the `-all` qualifier is reserved for a suite that fans
   out to every skill in its domain (`docs-all`). Umbrella renames from the draft
   stand: `project-commit → git-commit`, `lifecycle → lifecycle-run`,
   `post-pr-review-monitor → pr-monitor`, `repo-hygiene → repo-clean`,
   `auto-issue-dev → issue-dev-auto`.
4. **Exception list** (documented, enforced as the only allowed non-conformant names):
   - `help` — universal single-word entry point; ergonomics beat conformance.
   - `pass-cli` — named for the tool it wraps (the `pass-cli` binary). The draft's
     `token-fetch` is rejected: in this library the `token` domain means LLM token
     economy (`token-conserve`, `token-benchmark`); a credential fetcher named
     `token-fetch` invites misinvocation.
   - `graphify` — named for the managed `graphify` CLI it wraps; the service toggle
     (`--enable-graphify`) and installed binary share the name. Draft's `graph-map`
     rejected to keep skill ↔ tool discoverability.
   - `ai-hooks-integration` — **externally installed** via retired skill supply
     (`github.com/runkids/ai-hooks-integration`); not ours to rename without forking
     the upstream source. Draft's `hooks-integrate` rejected.
   - `speckit-*` is **not** an exception: `speckit` is a domain token (vendor
     namespace kept as purpose); `speckit-implement-review → speckit-audit-tasks`
     proceeds.
5. **Deprecation stubs**: **none**. Stubs with old names would themselves violate the
   conformance gate, cost context budget, and require `tool_policies` keys. Instead the
   migration removes every stale reference repo-wide, and the PR/issue closeout carries
   the full old→new mapping table for muscle memory.
6. **Duplicate merges before rename** (union of guidance, single surviving skill):
   - `memory-log-compress` + `session-memory-compress` → `memory-compress`
   - `bot-pr-triage` + `triage-bot-pr-flood` → `pr-triage-bots`
7. **Delivery shape**: one migration branch/PR with reviewable per-phase commits
   (spec+docs+lint → merges/deletion → renames by domain → regeneration), instead of
   the issue's suggested one-PR-per-domain. Rationale: cross-skill references span
   domains (a phased sequence leaves dangling `/old-name` mentions between merges),
   every phase pays the full regeneration cost, and serial PRs each block on human
   merge. The commit structure preserves per-phase reviewability.

## Ratified Rename Map (68 entries, 66 unique targets)

| Current | New | Domain |
|---|---|---|
| `api-bulk-endpoint-optimization` | `api-optimize-bulk` | api |
| `out-of-band-cache-warm` | `cache-warm-oob` | cache |
| `ci-workflow-trigger-security` | `ci-audit-triggers` | ci |
| `ci-lint-config-drift` | `ci-diagnose-drift` | ci |
| `secure-comment-triggered-workflow` | `ci-harden-workflow` | ci |
| `reproduce-gated-ci-failure-locally` | `ci-reproduce-failure` | ci |
| `cli-help-before-dependency-checks` | `cli-audit-help` | cli |
| `code-quality` | `code-audit` | code |
| `sync-configs` | `config-audit` | config |
| `debug-layered-config-substitution` | `config-debug-substitution` | config |
| `app-native-config-validation` | `config-validate-native` | config |
| `ingestion-table-idempotency` | `data-design-ingestion` | data |
| `live-data-validation` | `data-validate-live` | data |
| `wire-new-field-end-to-end` | `data-wire-field` | data |
| `deploy-drift-root-cause` | `deploy-diagnose-drift` | deploy |
| `retire-component-cleanup` | `deploy-retire-component` | deploy |
| `research-validate-design` | `design-validate` | design |
| `docker-published-port-firewall-audit` | `docker-audit-firewall` | docker |
| `containerized-internal-service-probe` | `docker-probe-internal` | docker |
| `docs-diagrams` | `docs-generate-diagrams` | docs |
| `docs-readme` | `docs-improve-readme` | docs |
| `health-check` | `env-check` | env |
| `project-commit` | `git-commit` | git |
| `locate-missing-artifact-across-git` | `git-find-artifact` | git |
| `refactor-go` | `go-refactor` | go |
| `auto-issue-dev` | `issue-dev-auto` | issue |
| `auto-dev-issue-prep` | `issue-prep-auto` | issue |
| `commit-issue-sync` | `issue-sync-commit` | issue |
| `pr-issue-sync` | `issue-sync-pr` | issue |
| `learning-loop` | `learning-capture` | learning |
| `lifecycle` | `lifecycle-run` | lifecycle |
| `llm-output-path-traversal-audit` | `llm-audit-traversal` | llm |
| `headless-llm-cli-seam` | `llm-invoke-stdin` | llm |
| `mcp-server-security-audit` | `mcp-audit` | mcp |
| `memory-log-compress` | `memory-compress` (merge) | memory |
| `session-memory-compress` | `memory-compress` (merge) | memory |
| `dashboard` | `metrics-report` | metrics |
| `refactor-node` | `node-refactor` | node |
| `address-pr-comments` | `pr-address-comments` | pr |
| `clean-pr-from-stale-base` | `pr-clean-base` | pr |
| `merge-stacked-pr-chain` | `pr-merge-stacked` | pr |
| `post-pr-review-monitor` | `pr-monitor` | pr |
| `reset-reapply-clean-pr` | `pr-reset-reapply` | pr |
| `pr-regression-smoke` | `pr-smoke` | pr |
| `bot-pr-triage` | `pr-triage-bots` (merge) | pr |
| `triage-bot-pr-flood` | `pr-triage-bots` (merge) | pr |
| `verify-premise` | `premise-verify` | premise |
| `diagnose-stalled-background-process` | `process-diagnose-stall` | process |
| `scaffold` | `project-scaffold` | project |
| `verify` | `project-verify` | project |
| `meta-prompt-optimize` | `prompt-optimize` | prompt |
| `refactor-python` | `python-refactor` | python |
| `repo-hygiene` | `repo-clean` | repo |
| `secret-safe-upstream-proxy` | `security-harden-proxy` | security |
| `security-finding-refutation` | `security-refute-findings` | security |
| `diff-security-review` | `security-review-diff` | security |
| `security-finding-triage` | `security-triage-findings` | security |
| `checkpoint` | `session-checkpoint` | session |
| `shell-sete-silent-abort-audit` | `shell-audit-errexit` | shell |
| `shell-pipefail-subshell-audit` | `shell-audit-pipefail` | shell |
| `refactor-shell` | `shell-refactor` | shell |
| `smoke-orchestrator` | `smoke-manage` | smoke |
| `architecture-decision-tradeoff-table` | `spec-decide-tradeoffs` | spec |
| `speckit-implement-review` | `speckit-audit-tasks` | speckit |
| `refactor-terraform` | `terraform-refactor` | terraform |
| `pin-known-bug-test-survives-fix` | `test-pin-bug` | test |
| `statistical-test-fixture-variance` | `test-vary-fixtures` | test |
| `token-economy` | `token-conserve` | token |

Deleted (deprecated, superseded by `smoke-orchestrator` → `smoke-manage`): `browser-test`.

Keepers (already conformant): `a11y-audit`, `ai-code-audit`, `antipattern-detect`,
`branch-clean`, `ci-setup`, `deploy-reconcile`, `docs-all`, `docs-improve`,
`issue-prioritize`, `issue-triage`, `performance-check`, `plan-manage`, `pr-review`,
`skill-evolve`, `spec-review`, `token-benchmark`, `ux-review`, `version-pin`, and the
4 exceptions above.

End state: **88 skills** (91 − 2 merged away − 1 deleted), all conformant or on the
exception list.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ratified convention with an enforced conformance gate (Priority: P1)

A maintainer (or an AI agent creating a skill) consults a single documented naming
standard (`docs/SKILL-NAMING.md`) listing the pattern, domain vocabulary, and
exceptions. An automated repository check fails any newly added or renamed skill whose
name does not conform, so the taxonomy cannot drift again.

**Why this priority**: Without the documented standard and gate, any rename sweep decays
immediately — the library got into this state precisely because no convention was
enforced at creation time.

**Independent Test**: Add a throwaway skill directory with a non-conformant name and run
the test suite; the conformance check must fail naming the offender. Add one with a
conformant name; the check must pass.

**Acceptance Scenarios**:

1. **Given** the naming standard is documented, **When** a contributor adds a skill named
   `fix-all-the-things-quickly`, **Then** the automated check fails, citing the pattern
   and the documented vocabulary.
2. **Given** the exception list contains `help`, `pass-cli`, `graphify`,
   `ai-hooks-integration`, **When** the check runs on the migrated library, **Then** it
   passes with zero violations.
3. **Given** a skill whose frontmatter `name:` differs from its directory name,
   **When** the check runs, **Then** it fails identifying the mismatch.

---

### User Story 2 - Duplicates merged, deprecated skill removed (Priority: P2)

A user invoking memory-compression or bot-PR-triage help finds exactly one skill for
each job, carrying the union of the previously split guidance. The deprecated
`browser-test` skill no longer appears anywhere.

**Why this priority**: Merging before renaming shrinks the map and prevents renaming
near-duplicates twice (the specs/003 adjudication lesson); overlap is today's worst
invocation confusion.

**Independent Test**: Search the library for the four old duplicate names and
`browser-test` — none exist; `memory-compress` and `pr-triage-bots` exist and each
covers both predecessors' trigger scenarios.

**Acceptance Scenarios**:

1. **Given** the merged `memory-compress` skill, **When** a user needs either
   log-compression or session-transcript distillation, **Then** the one skill's
   description covers both trigger phrasings.
2. **Given** the migrated library, **When** searching for `browser-test`, **Then** no
   skill directory, config key, generated rule, or doc reference remains.

---

### User Story 3 - Full rename migration with zero stale references (Priority: P3)

A user types a domain prefix (e.g. `/pr-`) and sees all of that domain's skills cluster
together. Every derived artifact (per-assistant guides, generated rules, command
reference, config registries, hint registry, tests) refers only to new names, and the
deployed assistant homes contain only new names after redeploy.

**Why this priority**: The payoff of the taxonomy — lexicographic clustering and
predictable discovery — only materializes when the whole map lands and nothing dangles.

**Independent Test**: Repo-wide search for every old name returns zero hits (outside
spec/history documents that intentionally record the mapping); the deployed-home
reconciliation preview reports no orphaned old-name skills after a fresh deploy.

**Acceptance Scenarios**:

1. **Given** the migration is complete, **When** listing the skill library
   alphabetically, **Then** all skills sharing a domain token are adjacent.
2. **Given** any old name from the map, **When** searching the repository (skills,
   configs, docs, tests, generated artifacts, extension hook wiring), **Then** the only
   hits are the spec, changelog/release notes, and the tracking issue.
3. **Given** a fresh deployment to the assistant homes, **When** the reconciliation
   preview runs, **Then** old-name skill copies are flagged for pruning (or already
   pruned) and every new name is present.

---

### Edge Cases

- The hint registry triggers on a `refactor-*` name glob; after language-first renames
  that glob matches nothing — the moment trigger must be updated to the new names, and
  a check should confirm every registry `command_refs` entry resolves to a real skill.
- The spec-toolchain's post-implementation hook wiring invokes
  `speckit-implement-review` by name; renaming it requires updating the hook
  registration, or implementation-review silently stops running.
- Generated per-skill rule files for the old names must be deleted, not just new ones
  added — a stale generated file resurrects the old name on the next drift check.
- The context-budget guard totals auto-loaded skill descriptions; renames change name
  lengths and merges remove entries — headroom must be re-measured, not assumed.
- Concurrent worktrees/branches created before the migration still reference old names;
  the mapping table in the issue closeout is the recovery path (no compatibility stubs).
- External retired skill supply-managed skill (`ai-hooks-integration`) must remain untouched, and
  the retired skill supply ignore/config state must not drop it from tracking.
- Runtime state outside the repository (deployed homes, SkillClaw session/evolve state,
  user memory files) may reference old names; only deployed homes are in scope
  (refreshed by redeploy) — others age out naturally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The naming standard MUST be documented in `docs/SKILL-NAMING.md`: the
  `<purpose>-<verb>[-<qualifier>]` pattern, the closed domain vocabulary (including
  multi-token purposes), verb guidance, qualifier rules, the exception list with
  per-entry rationale, and the process for adding a new domain token.
- **FR-002**: An automated check MUST fail the test suite when any skill in the library
  (a) has a name not matching the convention and not on the exception list, or
  (b) has frontmatter `name:` differing from its directory name.
- **FR-003**: The two duplicate clusters MUST be merged into `memory-compress` and
  `pr-triage-bots`, each preserving the union of its predecessors' guidance and
  trigger descriptions, before renames are applied.
- **FR-004**: The deprecated `browser-test` skill MUST be deleted along with every
  reference to it in configs, generated artifacts, docs, and tests.
- **FR-005**: All 68 map entries MUST be renamed exactly per the ratified map, with each
  skill's frontmatter `name:` equal to its new directory name.
- **FR-006**: All derived/generated artifacts MUST be regenerated so they carry only new
  names: per-assistant orchestration guides and indexes, generated per-skill editor
  rules (old-name rule files removed), and the human-readable command reference.
- **FR-007**: All configuration registries keyed by skill name MUST be updated 1:1 —
  tool policies, command categories, validation overrides, and the hint registry
  (including its `refactor-*` moment trigger) — preserving each entry's existing values.
- **FR-008**: A repo-wide sweep MUST remove every other old-name reference: cross-skill
  `/old-name` mentions in skill bodies, curated tables in README/CLAUDE.md/AGENTS.md and
  per-assistant guides, hardcoded names in shell/python tests, and the
  spec-toolchain hook wiring for the renamed implementation-review skill. Only the
  spec, the tracking issue, and changelog/release notes may retain old names (as the
  mapping record).
- **FR-009**: The full verification chain MUST pass after migration: repository
  pre-commit gates from the default-branch base, the shell and python test suites, and
  the context-budget guard (with headroom re-measured and its comment corrected).
- **FR-010**: After redeploying to the assistant homes, the deployed-state
  reconciliation MUST show old names pruned and new names present across all enabled
  assistant targets.
- **FR-011**: No compatibility stubs are created; the issue closeout MUST carry the
  complete old→new mapping table, and the tracking issue's acceptance checklist MUST be
  updated to reflect delivery.

### Key Entities

- **Skill**: a named directory with frontmatter (`name`, `description`); the name is
  the invocation surface (`/name`) and the sort key for discovery.
- **Rename Map**: the ratified old→new table above; the single source of truth for the
  migration and the closeout mapping record.
- **Domain Vocabulary**: the closed set of first-position purpose tokens; grows only by
  documented decision.
- **Exception List**: the only names allowed to bypass the convention, each with
  rationale (`help`, `pass-cli`, `graphify`, `ai-hooks-integration`).
- **Derived Artifacts**: generated files and config registries keyed by skill name that
  must stay 1:1 with the library (tool policies, categories, validation overrides, hint
  registry, editor rules, guides/indexes, command reference).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of skill names conform to the convention or appear on the documented
  4-entry exception list; the automated conformance check enforces this on every run.
- **SC-002**: Skills sharing a domain token sort adjacently: for every domain with ≥2
  skills, listing the library alphabetically shows them as one contiguous block.
- **SC-003**: A repository-wide search for each of the 71 retired names (68 renamed +
  2 merged-away + 1 deleted, counting merge sources) yields zero hits outside the spec,
  changelog/release notes, and the tracking issue.
- **SC-004**: The library shrinks from 91 to 88 skills with no loss of guidance (merged
  skills' trigger scenarios all present in their successors).
- **SC-005**: All repository gates pass on the migration branch from the default-branch
  base, and a fresh deploy leaves zero old-name orphans in any assistant home.
- **SC-006**: A newly added non-conformant skill is rejected by the test suite with an
  actionable message (pattern + vocabulary + exception process).

## Assumptions

- This is a single-maintainer library; besides the deployed assistant homes (refreshed
  by redeploy) there are no external consumers of skill names, so no deprecation window
  or compatibility stubs are needed (ratified decision 5).
- The issue's draft map is authoritative except where ratified otherwise here
  (decisions 2 and 4); no further per-name review is required before implementation.
- `speckit-*` core toolchain skills that live outside the shared library are vendor
  artifacts and out of scope; only the library-resident `speckit-implement-review` is
  renamed (staying within the `speckit` domain).
- The `auto-dev` issue LABEL is a user-facing API and is never renamed; only the skills
  formerly named `auto-issue-dev`/`auto-dev-issue-prep` change.
- Runtime state outside the repository (SkillClaw capture/evolve state, user memory,
  shell history) is out of scope; stale names there age out naturally.
- Delivery lands as one migration PR with per-phase commits (ratified decision 7),
  deviating deliberately from the issue's suggested one-PR-per-domain sequencing.
