# Feature Specification: New Agent Skills (Version Pinning, Docs Orchestration, PR Review, Branch Cleanup)

**Feature Branch**: `002-new-agent-skills`

**Created**: 2026-06-01

**Status**: Delivered 2026-06

**Input**: User description: "Add new skills to do the following: Skill: Enforce version pinning — specific version (avoid latest, recommended latest stable, or request version); ensure version pin also includes hash if supported; force it on specific file types / name as a hook (e.g. requirements.txt, docker-compose.yaml, common files that support version pinning). Skill: Create an all-in-one docs command that runs our existing DOCS in sub-agents in the appropriate order to support any order of precedency. Skill: GitHub PR Reviewer (review all open PRs, identify if they are needed...); GitHub/Git Branch Cleaner."

## Clarifications

### Session 2026-06-01

- Q: On the automatic hook path (tracked file saved), should version-pin auto-rewrite or warn-only? → A: Warn-only on the hook (report violations + exact fix, no silent rewrite mid-edit); on-demand invocation still auto-fixes.
- Q: How should version-pin resolve the latest-stable version and integrity hash? → A: Shell out to native package managers (pip/pip-compile, docker manifest/buildx, npm, etc.); degrade to a reported warning when the tool is absent.
- Q: What deletion scope should branch-clean operate on? → A: Local branches only by default; remote-branch deletion is opt-in behind a separate explicit flag.

## User Scenarios & Testing *(mandatory)*

This feature adds **four** independent skills to the Manifest agent-configuration repository. Each is a standalone slice of value and can be developed, tested, and demonstrated on its own.

### User Story 1 - Enforce Version Pinning (Priority: P1)

A contributor edits a dependency-bearing file (e.g. `requirements.txt`, `docker-compose.yaml`, a Dockerfile, or a GitHub Actions workflow) that references a dependency loosely — `latest`, an unbounded range, or a pin with no integrity hash. The version-pinning skill detects the loose reference, resolves the latest stable specific version (and a supported integrity hash where the ecosystem provides one), and rewrites the reference in place to a fully pinned form. The skill can also run on demand against a path or the working tree, and can be wired as an automatic hook scoped to recognized file types/names so the check fires whenever those files are written.

**Why this priority**: Loose version references are the highest-risk item — they cause non-reproducible builds and are a supply-chain attack vector. Pinning with hashes is a Tier-1 security concern in this repo's validation criteria.

**Independent Test**: Point the skill at a fixture `requirements.txt` containing `requests` (unpinned) and a `docker-compose.yaml` using `image: postgres:latest`. Confirm the skill rewrites them to a specific version plus hash where supported, leaves already-correctly-pinned entries untouched, and honors an explicit bypass marker.

**Acceptance Scenarios**:

1. **Given** a `requirements.txt` line `requests` (no version), **When** the skill runs, **Then** it is rewritten to a specific latest-stable version with the ecosystem-supported integrity hash (e.g. `requests==X.Y.Z --hash=sha256:...`).
2. **Given** a `docker-compose.yaml` service using `image: postgres:latest`, **When** the skill runs, **Then** the tag is replaced with a specific version and a digest (`postgres:X.Y@sha256:...`) where the registry supports it.
3. **Given** an entry already pinned to a specific version with a hash, **When** the skill runs, **Then** the entry is left unchanged and reported as compliant.
4. **Given** a line carrying an explicit bypass marker (an allowed exception), **When** the skill runs, **Then** that line is skipped, left unmodified, and the bypass is recorded in the run summary.
5. **Given** the skill is registered as a hook for tracked file types, **When** one of those files is written/saved, **Then** the pinning check fires automatically against just that file in **warn-only** mode — it reports violations and the exact pinned+hashed fix but does not rewrite the file mid-edit (the user applies the fix via on-demand invocation or confirmation).
6. **Given** a requested version is supplied for a dependency, **When** the skill runs, **Then** it pins to that exact requested version (plus hash) rather than latest stable.

---

### User Story 2 - All-in-One Documentation Refresh (Priority: P2)

A maintainer wants to refresh all project documentation in a single command rather than running `docs-readme`, `docs-diagrams`, and `docs-improve` by hand. They invoke the all-in-one docs skill, which dispatches the existing docs skills as sub-agents, choosing the execution order per run based on what changed (with a documented default precedence as fallback), respecting dependencies between them, and returns one consolidated report.

**Why this priority**: High convenience and consistency value, but it composes existing, already-working skills rather than introducing new capability, so it ranks below the security-critical pinning skill.

**Independent Test**: Run the all-in-one docs skill on the repo and confirm it invokes all three existing docs skills as sub-agents, produces a single merged summary identifying which ran, in what order, and why, and that the order adapts when only (say) diagrams-relevant files changed.

**Acceptance Scenarios**:

1. **Given** the three docs skills exist, **When** the all-in-one skill runs, **Then** each is dispatched as an independent sub-agent and all results are aggregated into one report.
2. **Given** recent changes touch only architecture/structure, **When** the skill chooses an order, **Then** it prioritizes the diagram-relevant skill while still documenting the precedence it applied.
3. **Given** no special context, **When** the skill runs, **Then** it falls back to a documented default precedence and states this in the report.
4. **Given** one sub-agent fails, **When** the run completes, **Then** the failure is surfaced in the report without silently dropping the other results.

---

### User Story 3 - Review All Open Pull Requests (Priority: P2)

A maintainer wants to understand the state of every open PR on the active platform (GitHub primarily, with the repo's existing GitLab abstraction respected where present). The PR-review skill enumerates all open PRs, assesses each for whether it is still needed, mergeable, stale, superseded, or in conflict, and returns a prioritized, actionable summary with a recommended disposition per PR. The skill is analysis-only by default and does not merge, close, or modify PRs without explicit confirmation.

**Why this priority**: Strong workflow value for keeping the PR queue healthy, and it builds on the repo's existing `git_ops.sh` / platform-detection scripts, so it is well-scoped but not security-critical.

**Independent Test**: Run the skill against a repo with multiple open PRs and confirm it lists each with a recommended disposition (keep/merge/close/needs-rebase/superseded) and a one-line rationale, performing no mutations.

**Acceptance Scenarios**:

1. **Given** several open PRs, **When** the skill runs, **Then** it returns one row per PR with status, mergeability, staleness, and a recommended disposition with rationale.
2. **Given** a PR whose branch is already merged or whose changes are superseded, **When** the skill runs, **Then** it flags the PR as a candidate to close.
3. **Given** the skill is invoked without an explicit action flag, **When** it completes, **Then** it makes no changes to any PR (analysis-only).
4. **Given** no open PRs exist, **When** the skill runs, **Then** it reports a clean queue without error.

---

### User Story 4 - Clean Up Stale Branches (Priority: P3)

A maintainer wants to prune branches that are no longer useful — branches already merged into the default branch, branches whose remote was deleted (`[gone]`), and branches with no activity past a staleness threshold. The branch-cleaner skill identifies these candidates, presents them grouped by reason, and deletes them only after explicit confirmation (with a dry-run preview by default). By default it operates on **local branches only**; remote-branch deletion is opt-in behind a separate explicit flag. Protected branches (default branch, release branches) are never proposed for deletion.

**Why this priority**: Useful housekeeping that reduces clutter, but lowest risk-reduction value and most easily deferred; deletion is destructive so safety gating matters most here.

**Independent Test**: Run the skill in a repo with a merged branch, a `[gone]` branch, and a protected branch; confirm it lists the first two as deletion candidates (grouped by reason), never lists the protected branch, and deletes nothing without confirmation.

**Acceptance Scenarios**:

1. **Given** a local branch fully merged into the default branch, **When** the skill runs, **Then** it is listed as a safe-to-delete candidate.
2. **Given** a local branch tracking a deleted remote (`[gone]`), **When** the skill runs, **Then** it is listed as a candidate with that reason.
3. **Given** the default branch and any protected branches, **When** the skill runs, **Then** they are never proposed for deletion.
4. **Given** no confirmation/`--apply` flag, **When** the skill runs, **Then** it only previews (dry-run) and deletes nothing.
5. **Given** confirmation is provided, **When** the skill applies, **Then** it deletes the confirmed branches and reports each deletion outcome (including failures).

---

### Edge Cases

- **Pinning — unresolvable version**: A dependency whose latest stable version cannot be resolved (offline, private registry, yanked release) must be reported as a non-fatal warning, not silently skipped or left in a broken state.
- **Pinning — no hash support**: For ecosystems/files where integrity hashes are not supported, the skill pins the specific version and notes that no hash was applicable, without failing.
- **Pinning — file-type coverage boundary**: A file type not in the recognized set is ignored by the hook; on-demand runs against an unrecognized file report "no applicable rules" rather than erroring.
- **Pinning — malformed file**: A syntactically broken target file is reported as a parse error and left untouched (no partial rewrites).
- **Docs orchestration — missing sub-skill**: If one of the three docs skills is unavailable, the all-in-one skill runs the remaining ones and reports the gap.
- **PR review — platform without API access / unauthenticated**: The skill reports that it cannot enumerate PRs and how to authenticate, rather than returning an empty "clean" result.
- **Branch cleanup — unmerged work**: A branch with unmerged commits is never proposed under the "merged" category and requires an explicit force path the skill does not take by default.
- **Branch cleanup — current branch**: The currently checked-out branch is never proposed for deletion.

## Requirements *(mandatory)*

### Functional Requirements

**Version-Pinning skill (`version-pin`)**

- **FR-001**: The skill MUST detect loose dependency references — `latest`, missing version, unbounded/open-ended ranges, and pins lacking an integrity hash — in recognized dependency files.
- **FR-002**: The skill MUST resolve target versions by shelling out to the ecosystem's native package-manager tooling (e.g. pip / pip-compile, `docker manifest`/buildx, npm), defaulting to the latest stable release or to an explicitly requested version when one is provided; when the required native tool is absent it MUST degrade to a reported warning rather than guessing.
- **FR-003**: The skill MUST include an integrity hash/digest in the pin wherever the target ecosystem's tooling supplies one (e.g. pip `--hash`, container image `@sha256:` digest, lockfile digests), and MUST note when hashing is not applicable.
- **FR-003a**: On explicit on-demand invocation, the skill MUST rewrite loose references in place to the resolved specific version (plus hash where supported).
- **FR-004**: The skill MUST support an explicit per-entry bypass mechanism so an intentional exception is left unmodified and recorded in the run summary.
- **FR-005**: The skill MUST be invokable on demand (against a path or the working tree) and MUST be registrable as an automatic hook scoped to a recognized set of file types/names (initial set MUST include at least `requirements.txt`, `docker-compose.yaml`/`docker-compose.yml`, Dockerfiles, and a documented, extensible list of other commonly version-pinned files). On the automatic hook path the skill MUST operate in **warn-only** mode — reporting violations and the exact pinned+hashed fix without rewriting the file mid-edit.
- **FR-006**: The skill MUST leave already-compliant entries unchanged and report them as compliant.
- **FR-007**: The skill MUST treat unresolvable versions, unsupported hashes, and unrecognized/malformed files as non-fatal, reported outcomes — never silent failures or partial corruption.

**All-in-one docs skill (`docs-all`)**

- **FR-008**: The skill MUST dispatch the existing `docs-readme`, `docs-diagrams`, and `docs-improve` skills as sub-agents.
- **FR-009**: The skill MUST choose execution order per run based on changed context, with a documented default precedence used as a fallback, and MUST honor any required ordering dependencies between the docs skills.
- **FR-010**: The skill MUST aggregate the sub-agent results into a single consolidated report that states which skills ran, in what order, and why.
- **FR-011**: The skill MUST surface a sub-agent failure in the report and continue running the remaining sub-agents rather than aborting the whole run.

**PR-review skill (`pr-review`)**

- **FR-012**: The skill MUST enumerate all open pull requests on the active platform, reusing the repo's existing platform-detection / git-ops abstraction.
- **FR-013**: For each open PR, the skill MUST assess and report status, mergeability, staleness, whether it appears superseded/already-merged, and a recommended disposition (e.g. keep, merge, close, needs-rebase) with a brief rationale.
- **FR-014**: The skill MUST be analysis-only by default and MUST NOT merge, close, or otherwise mutate any PR without explicit user confirmation.
- **FR-015**: The skill MUST handle the empty-queue and unauthenticated/no-API cases with clear messaging rather than a misleading "clean" result.

**Branch-cleaner skill (`branch-clean`)**

- **FR-016**: The skill MUST identify branch-deletion candidates grouped by reason: merged into the default branch, tracking a deleted remote (`[gone]`), and stale beyond a configurable threshold.
- **FR-016a**: The skill MUST operate on **local branches only by default**; deletion of remote branches MUST be opt-in behind a separate explicit flag and MUST NOT occur as part of the default local cleanup.
- **FR-017**: The skill MUST never propose protected branches (default branch, configured release/protected branches) or the currently checked-out branch for deletion.
- **FR-018**: The skill MUST default to a dry-run preview and MUST delete branches only after explicit confirmation/flag.
- **FR-019**: The skill MUST report the outcome of each attempted deletion, including failures, without silently swallowing errors.
- **FR-020**: The skill MUST never delete branches with unmerged commits via the default (safe) path.

**Cross-cutting (all four skills)**

- **FR-021**: Each skill MUST follow the repo's skill-authoring conventions: a `SKILL.md` with `name` and `description` frontmatter under `.skillshare/skills/<skill-name>/` (the source of truth), reachable via the `configs/claude/skills` compat symlink.
- **FR-022**: Each skill MUST register appropriate tool policies in `configs/claude/config/command_config.yml`, and add validation overrides in `configs/claude/config/validation_criteria.yml` where its default verdict criteria differ.
- **FR-023**: Each new skill MUST be documented in the repo's command/skill listings (CLAUDE.md and docs/COMMANDS.md as applicable) consistent with how existing skills are listed.

### Key Entities *(include if feature involves data)*

- **Dependency reference**: A single pinnable item in a target file — its name, current version expression, resolved specific version, and integrity hash/digest (where supported), plus a compliant/violation/bypassed state.
- **Pinning rule set**: The mapping of recognized file types/names to how their dependency references are parsed and what hash form (if any) applies.
- **PR assessment**: Per-PR record — identifier, title, author, age, mergeability, staleness, superseded/merged flags, recommended disposition, and rationale.
- **Branch candidate**: Per-branch record — name, local/remote, merged status, `[gone]` status, last-activity age, protected flag, and proposed action.
- **Docs run report**: The consolidated result of the orchestrated docs run — ordered list of sub-skills invoked, the precedence reasoning, and each sub-skill's outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the version-pinning skill on a file with N loose references produces a fully pinned file (specific version + hash wherever supported) with zero remaining loose references, except entries explicitly bypassed.
- **SC-002**: 100% of already-compliant entries are left byte-for-byte unchanged across repeat runs (the skill is idempotent — a second run reports no changes).
- **SC-003**: The version-pinning hook fires automatically on save/write for every file in the recognized set and for none outside it.
- **SC-004**: The all-in-one docs skill completes a full documentation refresh in a single invocation and produces one report covering all three docs skills, with the applied order and rationale stated.
- **SC-005**: The PR-review skill returns a disposition recommendation with rationale for 100% of open PRs and performs zero mutations when run without an explicit action.
- **SC-006**: The branch-cleaner skill proposes zero protected or current branches for deletion across all runs, and deletes nothing without explicit confirmation.
- **SC-007**: A maintainer can go from "no open-PR/branch overview" to a prioritized, actionable list in a single command for each of the PR-review and branch-clean skills.

## Assumptions

- The four capabilities are delivered as **four separate skills** (`version-pin`, `docs-all`, `pr-review`, `branch-clean`), per the user's choice, matching the repo's single-purpose skill convention.
- The version-pinning skill **auto-fixes in place on explicit on-demand invocation** (resolves and rewrites) with an **explicit bypass** mechanism for intentional exceptions; the **automatic hook path is warn-only** (reports the fix without mutating the file mid-edit), per the user's clarification.
- Version/hash resolution shells out to **native package-manager tooling** rather than bespoke registry calls, degrading to a warning when the tool is unavailable, per the user's clarification.
- The branch-cleaner skill operates on **local branches only by default**, with remote deletion gated behind a separate explicit flag, per the user's clarification.
- The docs skill **decides ordering per run** with a documented default precedence as fallback, per the user's choice.
- Skills live in `.skillshare/skills/` (source of truth) and are deployed to home targets by `bootstrap.sh`; `configs/claude/skills` is a compat symlink and must not be replaced with a real directory.
- "Latest stable" excludes pre-releases/release-candidates unless a pre-release is explicitly requested.
- The PR-review and branch-clean skills reuse the existing platform abstraction (`git_platform.sh` / `git_ops.sh`), defaulting to GitHub while respecting GitLab where detected; Linear is out of scope for these two.
- The version-pinning hook integration uses the repo's existing hook mechanism (the `ai-hooks-integration` skill) rather than introducing a new hook framework.
- Staleness and protected-branch definitions are configurable, defaulting to values consistent with existing repo config conventions.
- Network/registry access is available when resolving latest-stable versions and hashes; offline runs degrade to reported warnings rather than failures.
