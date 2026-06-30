# Feature Specification: Deploy Reconciliation Review (Orphan Detection)

**Feature Branch**: `368-deploy-orphan-review`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "Manifest: 1. Run a review when writing or potentially merging. provide an option to list all that would be kept (or removed) that don't exist in our project"

## Overview

Manifest deploys configuration from the repository (the project source of truth) into the user's home directory. Over time, items accumulate in the deployed location that no longer exist in the repository — for example a skill that was deleted from the repo but still sits in the deployed location, or a config file from an older layout. Today the deploy step only ever *adds and overwrites*; it never reports or removes these leftovers, so the deployed environment silently drifts from the project.

This feature adds a **reconciliation review** that compares the deployed environment against the project and reports every deployed item that does not exist in the project, classified as either **KEEP** (legitimately retained, e.g. user-owned files) or **REMOVE** (an orphan eligible for cleanup). The review is available on demand as a safe, read-only preview and also runs (report-only) as part of the write/deploy step.

Removal is **never the default and never a side effect of a routine deploy**. The review runs in preview (read-only) mode by default; it deletes orphans only when the user explicitly invokes its destructive mode (e.g. an explicit `--remove`/prune option), and only after a preview is available. The same review tool therefore has two modes — a safe default preview mode and an explicit destructive mode — rather than a separate utility.

To distinguish a genuine orphan (e.g. a skill deleted from the project, or a file from an older layout) from an arbitrary unrelated user file, the review operates over a defined **managed scope**: the set of deployment roots that Manifest owns and writes into across all assistant homes it deploys to — `~/.claude`, `~/.cursor`, `~/.gemini`, `~/.codex`, and `~/.antigravity`. These roots are Manifest-owned namespaces — users are not expected to author their own files directly inside them. A deployed item is an orphan only if it sits within that managed scope and has no corresponding current project source. Files outside the managed scope are never reconciled or removed.

Because the assistant homes mirror each other (the secondary homes symlink into the canonical `~/.claude` content), the review **resolves symlinks and deduplicates** so a single shared target is reconciled once and never double-reported or given conflicting KEEP/REMOVE verdicts across roots.

Orphans are detected and acted on at the granularity of a **deployable unit**: a skill is treated as its whole top-level directory, and config files are reconciled individually. The review does not descend into a skill that still exists in the project to flag files inside it, which avoids partially gutting a live skill.

The comparison is **stateless**: it compares the *current* deployed state against the *current* project. The feature does not maintain a historical record of past deploys, so "was this ever deployed by a previous version" is out of scope — anything present in a managed root with no current project source is treated as an orphan regardless of how it got there.

## Clarifications

### Session 2026-06-30

- Q: At what granularity should orphans be detected/reported/removed? → A: Deployable unit — a skill is its top-level directory (treated as one unit); config files are reconciled individually. The review does not descend into a still-present skill to flag internal files.
- Q: Which deployed locations should be reconciled, given the multi-assistant mirror layout? → A: All assistant homes (`~/.claude`, `~/.cursor`, `~/.gemini`, `~/.codex`, `~/.antigravity`); symlinked items are resolved and deduped so a shared target is not double-reported or given conflicting verdicts.
- Q: How should opt-in removal actually delete orphans? → A: Recoverable backup — removed items are moved to a timestamped backup/trash location and the location is reported, so an accidental removal can be restored (no hard delete by default).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview kept/removed items on demand (Priority: P1)

A maintainer wants to know, without changing anything, which deployed items no longer exist in the project. They run the review in preview (dry-run) mode and receive a list of every deployed item not present in the project, each labeled KEEP or REMOVE, with a short reason and a summary count.

**Why this priority**: This is the explicit core request ("provide an option to list all that would be kept or removed that don't exist in our project"). It is read-only, delivers immediate diagnostic value, and is safe to ship and run independently of any removal capability.

**Independent Test**: Delete a skill/config from the project source, run the review in preview mode, and confirm the now-orphaned deployed item appears in the REMOVE list with an accurate count — and that nothing in the deployed environment changes.

**Acceptance Scenarios**:

1. **Given** a deployed item that exists in the project, **When** the review runs in preview mode, **Then** that item is NOT listed (it is reconciled).
2. **Given** a deployed item that no longer exists in the project and is not protected, **When** the review runs in preview mode, **Then** it is listed under REMOVE with a reason and no change is made to the deployed environment.
3. **Given** a deployed item that does not exist in the project but is protected (user-owned), **When** the review runs in preview mode, **Then** it is listed under KEEP with the protection reason.
4. **Given** the deployed environment fully matches the project, **When** the review runs in preview mode, **Then** the output reports zero orphans.

---

### User Story 2 - Review surfaced during write/deploy (Priority: P2)

When a maintainer runs the deploy/write step, the reconciliation review runs automatically and surfaces a summary of orphaned deployed items (KEEP/REMOVE) so drift is caught at the moment new content is written, rather than discovered later.

**Why this priority**: Catching drift at deploy time is the "run a review when writing" half of the request and prevents accumulation, but it depends on the detection logic from Story 1, so it follows it.

**Independent Test**: With at least one orphan present, run the deploy/write step and confirm the orphan summary is shown as part of the deploy output without interrupting a successful deploy.

**Acceptance Scenarios**:

1. **Given** orphaned deployed items exist, **When** the write/deploy step runs, **Then** a reconciliation summary (counts of KEEP/REMOVE) is shown as part of deploy output.
2. **Given** no orphans exist, **When** the write/deploy step runs, **Then** the review reports a clean result and does not add noise or block the deploy.
3. **Given** the review runs during deploy, **When** it completes, **Then** it does not delete anything — a normal deploy is always report-only and removal requires the separate explicit action in User Story 3.

---

### User Story 3 - Opt-in removal of orphans (Priority: P3)

After reviewing the preview, a maintainer chooses to clean up. They explicitly opt in to removal; the system removes only items classified REMOVE, leaves KEEP items untouched, and reports what was removed.

**Why this priority**: Removal is the natural payoff but is destructive and lower priority than safe visibility. It must never be the default and depends on a trustworthy classification from Stories 1–2.

**Independent Test**: With one REMOVE orphan and one KEEP item present, run the review with removal explicitly enabled and confirm only the REMOVE item is gone, the KEEP item remains, and the action is reported.

**Acceptance Scenarios**:

1. **Given** items classified REMOVE and KEEP, **When** removal is explicitly enabled, **Then** only REMOVE items are moved to the backup location and KEEP items remain in place.
2. **Given** removal is requested without explicit opt-in, **When** the review runs, **Then** nothing is removed and the user is told how to opt in.
3. **Given** a removal completes, **When** it finishes, **Then** the system reports each removed item and the backup location from which it can be restored.

---

### Edge Cases

- **Shared / symlinked deployed items**: The secondary assistant homes symlink into the canonical `~/.claude` content, so the same skill is reachable from multiple roots. The review MUST resolve and deduplicate these (FR-017) so a shared target is reconciled once with a single verdict, and MUST treat a still-needed shared target as KEEP (FR-015) so a prune does not break linked consumers or leave dangling symlinks in another home.
- **User-owned items absent from the project**: Files the user owns or that hold local state/credentials (e.g. local settings, auth/state) legitimately do not exist in the project and MUST be classified KEEP, never REMOVE.
- **Disabled/toggled-off components**: Because detection is stateless, an item is judged purely on present-state: if a feature is toggled off and the current project would therefore not deploy it, any leftover deployed files for that feature DO appear as orphans (KEEP/REMOVE per policy) — which is the desired outcome, since toggled-off leftovers are exactly the drift to surface. An item never deployed simply isn't present and isn't reported.
- **Partial / interrupted prior deploy**: A clean deploy is expected to complete before the review reports a removal verdict; the review is run against a settled deployed state. The review MUST NOT delete anything during a deploy (removal is a separate explicit action), so a mid-deploy run can only ever *report*, never destroy in-progress files.
- **Empty or missing deployed location**: If nothing is deployed yet, the review reports zero orphans rather than erroring.
- **Items the deploy does not manage**: Files in the deployed location that are outside the set the deploy is responsible for MUST NOT be reported as removable orphans (the review only reconciles items within the deploy's managed scope).
- **Removal backup location**: The timestamped backup/trash location used by removal MUST itself be excluded from the managed scope / protected by policy, so a later review never reports or removes previously-backed-up items.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compare the deployed environment against the project source and identify every deployed item (within the deploy's managed scope) that does not exist in the project.
- **FR-002**: System MUST classify each such item as KEEP (retained) or REMOVE (removable orphan) and provide a human-readable reason for each classification.
- **FR-003**: System MUST provide an on-demand option to run the review in preview (dry-run) mode that lists all KEEP and REMOVE items and makes no changes to the deployed environment.
- **FR-004**: System MUST report a summary count (e.g. total orphans, removable, kept) alongside the per-item list.
- **FR-005**: System MUST run the reconciliation review as part of the write/deploy step and surface its summary in deploy output.
- **FR-006**: The write/deploy entry point MUST be report-only and MUST NOT delete anything under any option; orphan removal is performed exclusively by the review's explicit destructive action (FR-010), invoked as its own separate run, never as a side effect or option of a routine deploy.
- **FR-007**: System MUST classify user-owned items and local state/credential files that are absent from the project as KEEP, never REMOVE.
- **FR-008**: System MUST treat shared/linked deployed targets safely, so that removing an orphan does not silently break consumers that depend on a shared target.
- **FR-009**: System MUST only act on items within the deploy's managed scope and MUST NOT report unmanaged files in the deployed location as removable.
- **FR-010**: When removal is explicitly opted in, System MUST first present the full REMOVE list and require explicit confirmation before removing; it MUST then remove only items classified REMOVE, leave KEEP items untouched, and report each removed item. Removal MUST be **recoverable**: removed items are moved to a timestamped backup/trash location rather than hard-deleted, and the backup location MUST be reported so the user can restore. A documented non-interactive confirmation path MUST exist so the action can run in automation without a prompt.
- **FR-011**: System MUST default to non-destructive behavior: with no explicit removal opt-in, the review only lists and reports.
- **FR-012**: System MUST produce a clear "no orphans" result when the deployed environment fully matches the project.
- **FR-013**: System MUST define the **managed scope** explicitly — the deployment roots Manifest owns and writes into across all assistant homes it deploys to (`~/.claude`, `~/.cursor`, `~/.gemini`, `~/.codex`, `~/.antigravity`) — and MUST derive orphan status by comparing the contents of those roots against the items the current project would deploy into them. An item is an orphan only if it lies within a managed root and has no corresponding current project source. (Resolves: deleted-from-project items are detectable because they still sit in a managed root, while files outside managed roots are never flagged.)
- **FR-017**: System MUST resolve symlinks and deduplicate across the assistant homes so that a shared target reachable from multiple roots is reconciled once, reported once, and never given conflicting KEEP/REMOVE verdicts.
- **FR-018**: System MUST operate at the granularity of a **deployable unit** — a skill is reconciled as its whole top-level directory; config files are reconciled individually. The review MUST NOT descend into a skill that still exists in the project to flag files within it.
- **FR-014**: System MUST apply a **protection policy** — a defined, documented, and extensible set of path/name patterns for user-owned, local-state, and credential/auth items — and classify any orphan matching the policy as KEEP. The default protected set MUST cover the project's known user-owned artifacts (e.g. local settings and auth/state files), and the policy MUST be overridable so a user can add their own protected paths. An orphan inside a managed root that matches no protection pattern is a REMOVE candidate; the preview-first, explicit-opt-in flow (FR-003/FR-006/FR-010) is the safeguard that lets a user catch and protect any such item before removal. (This is the concrete mechanism backing FR-007.)
- **FR-015**: System MUST determine whether an orphan is a shared target with active dependents (e.g. other deployed configurations that link to it) and, if active dependents exist, classify it KEEP with a reason naming the dependency; only shared targets with no remaining active dependents are eligible for REMOVE. (This is the concrete mechanism backing FR-008.)
- **FR-016**: Active-dependent detection MUST be bounded to Manifest's own deployment roots and the known deployed assistant/config locations (not a full-filesystem traversal), so the review stays within the deploy-time performance budget (SC-006) while still covering the consumers Manifest itself creates.

### Key Entities *(include if feature involves data)*

- **Project source item**: An item that exists in the repository and is intended for deployment (the source of truth for what *should* be deployed).
- **Deployed item (deployable unit)**: A unit present in the deployed environment within the managed scope — a skill (its whole top-level directory) or an individual config file (FR-018).
- **Orphan**: A deployed unit with no corresponding project source item.
- **Disposition**: The classification applied to an orphan — KEEP (protected/user-owned/shared-and-needed) or REMOVE (eligible for cleanup) — together with a reason.
- **Reconciliation report**: The output of a review run: the per-item list of orphans (deduped across assistant homes) with dispositions and reasons, plus summary counts.
- **Removal backup**: A timestamped location where removed orphans are moved (not hard-deleted), enabling restore.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can list every deployed item that no longer exists in the project, each labeled KEEP or REMOVE, in a single command/run.
- **SC-002**: The preview run is non-destructive — 100% of preview runs leave the deployed environment byte-for-byte unchanged.
- **SC-003**: Orphan detection accuracy is 100% on a known fixture: every removed-from-project item is reported, and zero reconciled items are falsely reported.
- **SC-004**: Zero items matching the protection policy (user-owned / local-state / credential patterns, including user-added overrides) are ever classified REMOVE; and because removal is preview-first and opt-in, zero protected items are ever deleted without the user having had a chance to review the REMOVE list.
- **SC-005**: When removal is opted in, only REMOVE items are removed and 0 KEEP items are affected.
- **SC-008**: Every removal is recoverable — 100% of removed items are retrievable from the reported backup location immediately after removal.
- **SC-006**: The deploy step surfaces the reconciliation summary on every run and adds no perceptible delay to a clean deploy (orphan check completes within the existing deploy's time budget).
- **SC-007**: A maintainer can go from "noticed drift" to "previewed exactly what would be removed" without making any change to the deployed environment.

## Assumptions

- "Our project" = the repository (the configuration source of truth); "kept or removed that don't exist in our project" = deployed items with no corresponding source in the repository.
- "Run a review when writing or potentially merging" maps to running the review as part of the write/deploy step; an automatic pre-merge CI gate is explicitly OUT OF SCOPE for this feature (confirmed with the requester). "Potentially merging" is interpreted as the deploy operation merging repository content into the existing deployed tree.
- The default mode is preview/dry-run (non-destructive). Removal is a separate, explicit action and is never a side effect of a routine deploy (FR-006/FR-010). Removal is **recoverable** — removed items are moved to a reported timestamped backup location rather than hard-deleted (FR-010/SC-008).
- **Managed scope** is the set of deployment roots Manifest owns across all assistant homes it deploys to (`~/.claude`, `~/.cursor`, `~/.gemini`, `~/.codex`, `~/.antigravity`). Orphan detection compares the contents of those roots against what the current project would deploy; items in a managed root with no current project source are orphans. Symlinked/shared targets are resolved and deduped so a shared item is reconciled once (FR-017). Arbitrary user files outside managed roots are out of scope and never reported (FR-013).
- Detection, reporting, and removal operate at **deployable-unit** granularity: a skill = its whole top-level directory; config files individually. The review does not descend into a still-present skill to flag internal files (FR-018).
- A **protection policy** determines KEEP vs REMOVE: user-owned files, local state/credentials, and shared targets that active dependents still rely on are protected (KEEP). The protected set has sensible documented defaults and is user-overridable (FR-014). All other orphans within a managed root are REMOVE candidates.
- Shared-target safety is determined by detecting active dependents (e.g. links pointing at the deployed target); a shared target is only REMOVE-eligible once it has no remaining active dependents (FR-015). Dependent detection is bounded to Manifest's deployment roots and known deployed config locations rather than a full-filesystem scan, keeping it within the deploy-time budget (FR-016/SC-006).
- Detection is a **stateless** current-deployed-vs-current-project comparison; Manifest does not track deploy history, so distinguishing "never deployed" from "deployed by an older version" is out of scope. Removal is always preview-first and explicitly opted in, which is the safety net for any item an automated rule misclassifies.
- The feature operates on the local machine's deployed environment; it does not reconcile remote or other users' environments.
