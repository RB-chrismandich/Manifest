# Feature Specification: Skill Library Consolidation & Repo Health Hardening

**Feature Branch**: `003-skill-library-consolidation`

**Created**: 2026-06-10

**Status**: Delivered 2026-06

**Input**: User description: "End-to-end review findings: consolidate ~15 near-duplicate skills across 6 clusters (81 → ~67), fix documentation drift (stale counts/tables/changelog), harden script robustness (python3 -c interpolation, evolve timeout, set -u array sweep, misplaced test files), close test/CI gaps, and repo hygiene (records/, stale specs, error-message conventions)."

## Clarifications

### Session 2026-06-10

- Q: Is propagating skill deletions to deploy targets (home deploys copied by
  bootstrap, retired skill supply-managed targets) in scope, given stale copies would
  otherwise linger on deployed machines and negate the consolidation's
  benefit in live sessions? → A: In scope — deploy/sync tooling must remove
  skills no longer present in the source of truth (prune on deploy), verified
  by a test.
- Q: Which error-output convention is canonical for FR-017? → A: `err()`
  (script-name-prefixed, stderr) everywhere in `configs/claude/scripts/`;
  bootstrap libs keep `print_error()` (colored interactive output) as the
  documented exception for `bootstrap/lib/` only.
- Q: Where does the FR-011 empty-array guard live? → A: Both layers — a
  pre-commit hook for local commit-time feedback plus the same check as a CI
  lint step, so PRs from environments without pre-commit installed are still
  caught.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Skill library consolidation (Priority: P1)

A Claude Code user working in any session gets exactly one well-named skill per
workflow. Today, three near-identical "address PR comments" skills (and five
other duplicate clusters) split trigger probability so that no variant fires
reliably, and all 81 descriptions are loaded into every session's context.
After consolidation, each workflow has a single skill whose description covers
all of its trigger variants, the library shrinks to ~67 skills, and per-session
context cost drops accordingly.

**Why this priority**: Highest leverage — duplicates actively degrade skill
triggering (the library's core function) in every session, on every deployed
machine. The owner has explicitly approved merge/delete.

**Independent Test**: Can be fully tested by listing `.retired skill supply/skills/`,
confirming each consolidated cluster has exactly one surviving skill whose
SKILL.md covers the merged variants' content, and confirming the deleted
variants are gone.

**Acceptance Scenarios**:

1. **Given** the six identified clusters, **When** consolidation lands, **Then**
   each cluster resolves per the approved plan:
   - PR comments: 3 → 1 (`address-pr-comments` survives, body covers inline
     comments, review bodies, and issue-level discussion)
   - Session memory: 2 → 1 (`session-memory-compress` survives with both modes)
   - Live-data validation: 4 → 1 (single skill with smoke / before-merge /
     after-green modes)
   - Premise verification: 5 → 1 (single skill with CLI, API-schema, and
     image-runtime subsections)
   - Component retirement: 3 → 1 (single skill with daemon / tool-runtime /
     plugin-MCP subsections)
   - PR history repair: both kept, each gains a one-line decision anchor
     pointing to the other
2. **Given** a merged skill, **When** its SKILL.md is read, **Then** no
   procedure step or trigger condition present in any deleted variant is lost.
3. **Given** the consolidation is complete, **When** skills are counted,
   **Then** the total is 81 − 12 = 69 (±1 if a cluster decision changes during
   review; planning verified the cluster table yields 12 deletions: 2+1+3+4+2).
4. **Given** the consolidation lands via the repo's normal review flow,
   **When** the change is proposed, **Then** it arrives as a reviewable change
   set (the skill library's PR-gate discipline applies; no direct writes).
5. **Given** the skill-evolution pipeline runs after consolidation, **When** it
   builds its existing-library prompt, **Then** the prompt includes each
   skill's name **and description** (not name only), so deleted variants are
   not re-proposed under new names.
6. **Given** a machine with a previously-deployed skill set, **When** the
   deploy/sync tooling runs after consolidation, **Then** skills no longer in
   the source of truth are removed from the deploy targets (no stale
   duplicates remain to compete with merged survivors in live sessions).

---

### User Story 2 - Documentation accuracy restoration (Priority: P2)

A new user (or a deployed agent) reading the repo's documentation gets numbers
and command tables that match reality. Today the docs claim 28 skills (actual:
81), four command tables disagree with each other, the changelog lists shipped
features as unreleased, and a published analysis report describes a script
retired months ago.

**Why this priority**: The docs are this repo's product — they are deployed to
`~/` on target machines and directly shape agent behavior. Drift is high-impact
but the fix is mechanical.

**Independent Test**: Can be tested by grepping the named files for the stale
claims and confirming each is corrected, and by diffing the four command tables
against the canonical source.

**Acceptance Scenarios**:

1. **Given** AGENTS.md and README.md, **When** read after the fix, **Then** the
   stated skill count matches the actual count of SKILL.md files at the time of
   the change.
2. **Given** the four command tables (root CLAUDE.md, AGENTS.md,
   configs/claude/CLAUDE.md, docs/COMMANDS.md), **When** compared after the
   fix, **Then** docs/COMMANDS.md is the canonical source and the other three
   match it in rows, wording, and flags (per the owner's decision).
3. **Given** CHANGELOG.md, **When** read after the fix, **Then** shipped
   features (e.g., the promote audit log) appear under a dated release section,
   not "[Unreleased]".
4. **Given** docs/SHELL_ANALYSIS_REPORT.md, **When** read after the fix,
   **Then** it is either archived with a clear deprecation banner or
   regenerated against the current script set (no references to retired
   scripts presented as current).
5. **Given** the stale "Last Updated" stamps on root CLAUDE.md and AGENTS.md,
   **When** the docs are refreshed, **Then** the stamps reflect the refresh
   date.
6. **Given** a reader wondering which spec/plan system to use, **When** they
   consult the docs, **Then** a short map exists explaining the roles of
   specs/, .specify/, configs/claude/.plans/, and docs/superpowers/ (and the
   .Jules/ journal is referenced or relocated, not orphaned).

---

### User Story 3 - Script robustness fixes (Priority: P3)

An operator running the repo's CLI scripts is protected from quoting bugs and
hangs: file paths containing quotes no longer break (or worse, get interpreted
as code by) the YAML-parsing helpers; the skill-evolution pipeline cannot hang
forever on an unresponsive CLI; the empty-array-under-strict-mode bug class
fixed today in label_sync.sh cannot silently recur elsewhere; and test files
are no longer shipped inside the deployed scripts directory.

**Why this priority**: Each fix is small, but the failure modes (silent
breakage, indefinite hangs, accidental code execution on hostile paths) are the
kind that erode trust in automation. Lower than P1/P2 only because real-world
exploitability is limited to local CLI use.

**Independent Test**: Each fix is independently verifiable: run the affected
script against a path containing a single quote; run evolve against a stubbed
hung CLI; sweep all shell sources for the empty-array pattern; list the
deployed scripts directory for test files.

**Acceptance Scenarios**:

1. **Given** a labels/test-prompt file whose path contains a single quote,
   **When** label_sync.sh or browser_test.sh parses it, **Then** parsing
   succeeds (the path is passed as data, never interpolated into interpreter
   source).
2. **Given** the evolve pipeline invokes the headless CLI and the CLI hangs,
   **When** a per-chunk time limit elapses, **Then** the chunk fails with a
   clear error and the pipeline's existing fail-continue behavior applies
   (no indefinite hang).
3. **Given** all shell scripts in the repo (including bootstrap libraries),
   **When** swept for array expansions that can be empty under strict mode,
   **Then** every such site uses a safe expansion pattern, and the guard runs
   in both pre-commit and CI so new violations are caught before merge
   regardless of where the change originates.
4. **Given** the deployed scripts directory, **When** listed after the fix,
   **Then** no test files remain in it (they live under the repo's tests tree),
   and nothing that referenced them at their old location breaks.

---

### User Story 4 - Test & CI gap closure (Priority: P4)

A contributor changing the knowledge-base capture script (or other currently
untested scripts) gets test feedback before merge instead of silent breakage.
CI installs the same pinned tool versions as local pre-commit, and repeat runs
stop paying the dependency-install tax.

**Why this priority**: Real work (~1 day for the largest script) with
meaningful but less immediate payoff than P1–P3. The knowledge-base script
mutates persistent YAML state — the highest-risk untested surface.

**Independent Test**: Run the new test suites locally and in CI; compare CI
tool versions against pre-commit pins; measure CI run time before/after
caching.

**Acceptance Scenarios**:

1. **Given** the knowledge-base capture script's five subcommands, **When** the
   new test suite runs, **Then** each subcommand has at least one behavioral
   test (including the missing-knowledge-base error path), and the suite runs
   in CI.
2. **Given** the readiness-check and rules-generation scripts, **When** their
   new test suites run, **Then** core behaviors (config parsing, output
   shape, drift detection) are covered.
3. **Given** the CI workflow, **When** inspected after the fix, **Then**
   linting/test tools are version-pinned consistently with pre-commit, and
   dependency caching is enabled.

---

### User Story 5 - Repository hygiene (Priority: P5)

A maintainer browsing the repo finds no ambiguous untracked directories, no
"active" plans for delivered work, and consistent script conventions.

**Why this priority**: Minutes of work each; low standalone impact; batched
last.

**Independent Test**: `git status` is clean of ambiguous untracked paths; the
delivered spec is archived; convention checks pass.

**Acceptance Scenarios**:

1. **Given** the `records/` directory at the repo root, **When** its origin is
   verified (suspected: a capture/eval tool side-effect; owner believes
   SkillClaw-adjacent), **Then** it is gitignored (per the owner's decision)
   and its origin is noted in the change description so the producing tool can
   be identified later.
2. **Given** `specs/002-new-agent-skills/`, **When** its deliverables are
   reviewed, **Then** it is archived if delivered (and the root CLAUDE.md
   pointer to it as "the current plan" is updated), or its status is refreshed
   if genuinely active.
3. **Given** the repo's shell scripts, **When** error output is emitted,
   **Then** scripts in `configs/claude/scripts/` use the `err()` convention
   (bootstrap libs' `print_error()` being the documented exception), and the
   user-facing scripts lacking `--help` (8 identified in planning; 2 internal
   helpers exempted with rationale) gain it.

### Edge Cases

- A deleted skill name is referenced somewhere (docs, another skill's body,
  sync tooling state): consolidation must include a repo-wide reference sweep
  so no dangling references remain.
- The skill-evolution pipeline proposes a deleted variant again on its next
  run: the library prompt enhancement (name + description) is the mitigation;
  the promote pipeline's existing classify/review gate is the backstop.
- Two merged variants contain contradictory guidance for the same step: the
  merge must reconcile explicitly (keep the stricter/safer rule) rather than
  concatenate contradictions.
- A command table consumer (e.g., generated Cursor rules) depends on the old
  wording: regeneration/drift checks must run after the docs are unified.
- The `records/` directory turns out to be load-bearing for some local tool:
  gitignoring does not delete it locally, so behavior is unchanged; the change
  description must note the uncertainty.
- A user has hand-added a personal skill directly to a deploy target (not via
  the source of truth): prune-on-deploy must not delete files the tooling did
  not deploy — pruning is scoped to tracked/deployed skill names only.
- CI caching serves a stale dependency after a pin bump: cache keys must
  include the pin source so bumps invalidate the cache.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The skill library MUST contain exactly one skill per identified
  duplicate cluster, per the approved consolidation table (PR comments 3→1,
  session memory 2→1, live-data validation 4→1, premise verification 5→1,
  component retirement 3→1; PR history repair keeps both with cross-references).
- **FR-002**: Every merged skill MUST preserve all distinct trigger conditions
  and procedure steps from its absorbed variants, reconciling conflicts in
  favor of the stricter rule.
- **FR-003**: Deleted skill names MUST NOT remain referenced anywhere in the
  repository (docs, other skills, configs, tooling state), excluding
  historical records (CHANGELOG and this feature's spec artifacts).
- **FR-004**: The consolidation MUST go through the skill library's standard
  review flow (reviewable change set; no unreviewed writes to the source of
  truth).
- **FR-005**: The skill-evolution pipeline's existing-library prompt MUST
  include each library skill's description alongside its name.
- **FR-005a**: Deploy/sync tooling MUST remove skills from deploy targets when
  they are no longer present in the source of truth (prune on deploy), and
  this pruning behavior MUST be covered by a test. Pruning MUST NOT touch
  files in a deploy target that the tooling did not put there.
- **FR-006**: All documentation skill counts MUST match the actual library
  count at change time, and the four command tables MUST be unified with
  docs/COMMANDS.md as the canonical source.
- **FR-007**: CHANGELOG.md MUST reflect shipped features under dated sections;
  stale analysis reports MUST be archived-with-banner or regenerated; stale
  "Last Updated" stamps MUST be refreshed.
- **FR-008**: A documentation map MUST exist describing the four spec/plan
  systems and the .Jules/ journal's role.
- **FR-009**: No script MAY interpolate externally-influenced values into
  interpreter source text; such values MUST be passed as data (arguments or
  stdin).
- **FR-010**: The skill-evolution pipeline MUST bound each model-CLI invocation
  with a time limit, failing that chunk into the existing fail-continue path.
- **FR-011**: All shell array expansions that can be empty under strict mode
  MUST use a safe pattern, and an automated guard MUST catch new violations in
  both layers: a pre-commit hook (local commit-time feedback) and the same
  check as a CI lint step (covers PRs from hosts without pre-commit).
- **FR-012**: Test files MUST NOT live in directories deployed to user
  machines.
- **FR-013**: The knowledge-base capture script's subcommands MUST have
  behavioral test coverage running in CI; the readiness-check and
  rules-generation scripts MUST have at least core-behavior coverage.
- **FR-014**: CI tool versions MUST be pinned consistently with pre-commit,
  and dependency caching MUST be enabled with pin-aware cache keys.
- **FR-015**: The `records/` directory MUST be gitignored, with its suspected
  origin documented in the change description.
- **FR-016**: Delivered specs/plans MUST be archived (or status-marked
  "Delivered" where the directory has no archive convention, e.g. `specs/`)
  and stale "current plan" pointers updated.
- **FR-017**: Shell scripts in `configs/claude/scripts/` MUST emit errors via
  the `err()` convention (script-name-prefixed, to stderr); `bootstrap/lib/`
  retains `print_error()` (colored interactive output) as the sole documented
  exception. All user-facing scripts MUST support `--help`.

### Key Entities

- **Skill**: A directory under the skill library containing a SKILL.md with
  name + description frontmatter and a procedure body. Identified by its
  directory name; loaded into every session's context via its description.
- **Duplicate cluster**: A set of skills addressing the same workflow whose
  descriptions compete for the same triggers. Resolution = one survivor
  absorbing the variants' content.
- **Command table**: A markdown table mapping slash commands to descriptions
  and parallel-agent policy, duplicated across four documents; canonical copy
  lives in docs/COMMANDS.md.
- **Existing-library prompt**: The skill-evolution pipeline's representation of
  already-known skills, used to suppress re-proposals; currently names-only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Skill library shrinks from 81 to 69 (±1) skills with zero loss of
  distinct trigger conditions or procedure content (verified by cluster-by-
  cluster review).
- **SC-002**: Per-session skill-description context cost drops proportionally
  (~15% fewer descriptions loaded — 12 of 81).
- **SC-003**: A repo-wide search for any deleted skill name returns zero
  references after consolidation, and after a deploy/sync run no deleted
  skill remains present in any deploy target.
- **SC-004**: All four command tables are textually consistent with the
  canonical source, and all stated skill counts match the actual count, on the
  day the docs change lands.
- **SC-005**: The next skill-evolution run after consolidation proposes zero
  skills that duplicate an existing library entry's workflow (observed over at
  least one full evolve cycle).
- **SC-006**: Scripts parse files at paths containing quote characters without
  error; the evolve pipeline survives a hung-CLI simulation within the
  configured time bound.
- **SC-007**: The strict-mode array sweep reports zero unsafe expansion sites,
  and the guard blocks a deliberately-introduced violation.
- **SC-008**: Previously-untested scripts named in this spec have test suites
  running in CI; CI runs complete measurably faster with caching (target: ≥20s
  median improvement).
- **SC-009**: `git status` on a fresh clone plus a normal workflow session
  shows no ambiguous untracked paths at the repo root.

## Assumptions

- The six-cluster consolidation table from the end-to-end review is the
  approved scope; clusters discovered later are out of scope for this feature.
- Survivor naming follows the review's recommendations (e.g.,
  `address-pr-comments`, `session-memory-compress`); reviewers may rename
  during PR review without re-specifying.
- `docs/COMMANDS.md` is the canonical command table per the owner's explicit
  decision; automatic generation of the table from skill frontmatter is a
  desirable follow-up but NOT in scope here (manual unification is).
- `records/` is believed to be a tool side-effect (owner suspects the
  SkillClaw toolchain; repo search found no producer). Gitignoring is safe
  because it does not delete local data; if the producer is identified during
  implementation, it should be named in the change description.
- The browser-test script's coverage is the lowest-value of the P4 items and
  may be descoped by the reviewer if effort runs long; the knowledge-base
  capture script's coverage may not be descoped.
- Splitting the 1,253-line Linear operations script is explicitly deferred
  ("only when next touched") and is not part of this feature.
- The repo's existing review/merge discipline (PR-gated, CI-green) applies to
  every change in this feature; no new process is introduced.
