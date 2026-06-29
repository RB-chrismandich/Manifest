# Contract: Provider abstraction — tier map, status map, reconciliation

**Feature**: 365-lifecycle-codification | Per research.md D3/D4/D5. Config-resident (`configs/claude/config/lifecycle_providers.yml` + reuse `labels.yml`), routed through the existing provider seam (`git_platform.sh` detection; `git_ops.sh`/`linear_ops.sh`; Jira via Atlassian MCP).

## Entry-point detection (FR-019)

Extend `git_platform.sh`-style detection to classify the entry string:

| Pattern (example) | provider | entity_id |
|---|---|---|
| `https://github.com/o/r/issues/42`, `o/r#42` | github | `o/r#42` |
| `https://gitlab.com/o/r/-/issues/42` | gitlab | `o/r#42` |
| Linear id/url (`ENG-123`, `linear.app/...`) | linear | `ENG-123` |
| `https://<site>.atlassian.net/browse/PROJ-123`, `PROJ-123` | jira | `PROJ-123` |

No match → error, **no track created** (FR-019).

## Tier → native-construct map (FR-013/014/015)

| Tier | github | gitlab | linear | jira |
|------|--------|--------|--------|------|
| 1 Initiative | Project V2 *(no native type → fallback)* | Epic *(Premium)* | Initiative | Initiative *(Adv. Roadmaps)* |
| 2 Epic | Milestone / parent Sub-Issue | Epic / parent Issue | Project | Epic |
| 3 Task | Issue | Issue | Issue | Story/Task |
| 4 Sub-Task | Sub-Issue (native) | child Issue | Sub-issue (`parentId`) | Sub-task |

**Edge model**: every node is issue-like; every parent↔child edge is the provider's native hierarchy link (GitHub Sub-Issues API, Linear `parentId`, Jira parent field, GitLab linked/child issue).

**Missing/renamed tier (FR-014)**: `missing_tier_behavior: error` (default) → emit a configuration error naming the unresolved tier; or `collapse-to-label` (declared per provider) → represent the absent tier via a label/parent-reference convention. **Never** silently mismap.

**Provisioning (FR-016)**: top-down only; obtain parent `external_id` before creating children. Partial failure → mark node `FAILED_PROVISION`, record `remote_recorded_id`, halt that subtree, flag for reconciliation. No transactional remote delete is attempted or promised.

## Canonical-status map (FR-021 / D5)

Collapse 9 phases → 4 canonical statuses (already in `labels.yml`):

| canonical_status | phases | github/gitlab/linear | jira |
|---|---|---|---|
| `planned` | specify…spec_review_product | label `planned` | transition→ "To Do"/backlog (by id) |
| `in-progress` | plan…implement | label `in-progress` | transition→ "In Progress" (by id) |
| `needs-review` | verify (awaiting human) | label `needs-review` | transition→ "In Review" (by id) |
| `done` | verify passed + merged | label `done` | transition→ "Done" (by id) |

Jira values MUST be **workflow transition IDs** resolved at run time via the MCP `getTransitionsForJiraIssue` (never free-text). Labels for the git/Linear providers reuse `label_sync.sh`.

## Loop-safe reconciliation (SC-010 / D5)

Each autodev-loop tick, per active track:
1. Read `local_status`, `tracker_shadow.last_synced_status`, live `tracker_status`.
2. **Only tracker changed** (`tracker ≠ shadow`, `local = shadow`) → adopt tracker into local state (human moved it).
3. **Only local changed** → push local → tracker (label set or Jira transition), update `shadow`.
4. **Both changed** → conflict: flag `needs-human`, do not auto-resolve.
5. **Origin suppression**: after any push, set `shadow = pushed value` so the loop's own echo is not re-processed (prevents infinite loops).

All provider writes idempotent (re-applying a label/transition already in place is a no-op) (FR-022).

## Jira access (FR-020 / D3)

Direct via pre-authenticated Atlassian MCP — no bespoke auth. Tools used: `getJiraIssue`, `getTransitionsForJiraIssue`, `transitionJiraIssue`, `searchJiraIssuesUsingJql`, `getJiraProjectIssueTypesMetadata`/`getJiraIssueTypeMetaWithFields` (tier classification + missing-tier detection), `getVisibleJiraProjects`, `createJiraIssue` (provisioning), `addCommentToJiraIssue`. Implementation task: wire the `atlassian` server (already in `mcp_servers.yml`) into `settings.local.json`.
