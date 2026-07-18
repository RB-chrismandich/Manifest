# Tracker Abstraction — Contract-Test Matrix (Task 12)

> Acceptance gate for the tracker abstraction (Phase 1). Spec:
> [2026-07-16-agent-app-agnostic-skills-design.md](2026-07-16-agent-app-agnostic-skills-design.md).
> Plan task: `docs/superpowers/plans/2026-07-16-agent-app-agnostic-skills.md`, Task 12.

## Scope note (deviation from the original plan text)

The original plan called for live-testing all four providers (github, gitlab,
linear, jira) in this pass. Per explicit user direction on 2026-07-17, **only
the github column was run live** in this pass — no credentials were available
in this environment for the other three (`glab` not installed, no
`LINEAR_API_KEY`, no Atlassian MCP connection). gitlab/linear/jira are marked
`SKIPPED`, not `PASS` — an unverified path is never rendered as a silent green
(spec Principle 5). `providers.github.verified` in
`configs/claude/config/tracker_providers.yml` is flipped to `true`; gitlab/
linear/jira remain `false`.

## Test method (github)

All commands run against the real `RB-chrismandich/Manifest` repo (this repo,
confirmed via `gh repo view`) using `configs/claude/scripts/tracker_ops.sh
--provider github <verb> ...`, `gh` already authenticated as `RB-chrismandich`.
Two throwaway issues, both titled with a `[test-tracker-ops]` prefix, were
created for isolation and closed by the end of the run:

- **#596** — `[test-tracker-ops] contract matrix scratch issue (Task 12)` —
  exercised issue-view / issue-comment / issue-label / issue-transition /
  duplicate-mark. Closed by `duplicate-mark`.
- **#597** — `[test-tracker-ops] issue-close direct-verb scratch (Task 12)` —
  dedicated to exercising the `issue-close` verb directly (since
  `duplicate-mark` already closes #596 via its own internal call to the same
  `issue-close` code path, a second scratch issue gives a direct-invocation
  evidence trail rather than relying on an indirect one). Closed immediately
  after creation.

No labels were created solely for this test — `duplicate`, `needs-review`,
`done`, `planned`, `in-progress` all pre-exist in the repo's label set
(provisioned by Task 4 / `label_sync.sh`, confirmed via `gh label list` before
testing). Nothing was left in an open/dirty state; see Cleanup below.

## Matrix

| Canonical operation | github | gitlab | linear | jira |
|---|---|---|---|---|
| `resolve-provider` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-list` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-create` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-view` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-comment` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-label` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `issue-transition` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `duplicate-mark` | PASS | SKIPPED | SKIPPED | SKIPPED |
| `sub-issue-create` | N/A (exit 4, documented gap) | SKIPPED | SKIPPED | SKIPPED |
| `sub-issue-list` | N/A (exit 4, documented gap) | SKIPPED | SKIPPED | SKIPPED |
| `issue-close` | PASS | SKIPPED | SKIPPED | SKIPPED |

**Result: 9/9 applicable github operations PASS; 2/2 N/A cells match documented
behavior (exit 4 — "not implemented for provider", registry §4.1 mapping).**
gitlab/linear/jira: SKIPPED 2026-07-17 — no credentials in this environment.

## Evidence (github)

### `resolve-provider` — implicit, exercised by every call below

Every command below resolves to `github` via `git_platform.sh` detecting the
`RB-chrismandich/Manifest` origin remote; no `--provider github` override was
strictly required, but it was passed explicitly per the task brief for
unambiguous evidence.

### `issue-list` — PASS

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-list --limit 5
18	OPEN	Dependency Dashboard	chore, dependencies	2026-06-13T03:45:26Z
```
Exit 0. Real open issue returned (Renovate's Dependency Dashboard, issue #18).

### `issue-create` — PASS

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-create \
    --title "[test-tracker-ops] contract matrix scratch issue (Task 12)" \
    --body "Scratch issue created by the Task 12 tracker_ops.sh contract-test matrix..."
https://github.com/RB-chrismandich/Manifest/issues/596
```
Exit 0. Issue #596 created.

### `issue-view` — PASS

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-view 596
title:	[test-tracker-ops] contract matrix scratch issue (Task 12)
state:	OPEN
author:	RB-chrismandich (Chris Mandich)
...
number:	596
```
Exit 0. Matches the just-created issue.

### `issue-comment` — PASS

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-comment 596 \
    "test comment from tracker_ops contract matrix"
https://github.com/RB-chrismandich/Manifest/issues/596#issuecomment-5006983932
```
Exit 0. Comment posted and visible at the returned URL.

### `issue-label` — PASS

The `duplicate` label from Task 4 exists on this repo (confirmed via `gh label
list` and cross-checked against `configs/claude/config/labels.yml` — no
substitution needed).

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-label 596 --add-label duplicate
https://github.com/RB-chrismandich/Manifest/issues/596

$ gh issue view 596 --json labels -q '.labels[].name'
duplicate
```
Exit 0. Label applied and verified via a separate `gh` read (not just the
tool's own stdout).

### `issue-transition` — PASS (label-swap behavior confirmed both directions)

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-transition 596 needs-review
https://github.com/RB-chrismandich/Manifest/issues/596
$ gh issue view 596 --json labels -q '.labels[].name'
duplicate
needs-review

$ configs/claude/scripts/tracker_ops.sh --provider github issue-transition 596 done
https://github.com/RB-chrismandich/Manifest/issues/596
$ gh issue view 596 --json labels -q '.labels[].name'
duplicate
done
```
Exit 0 both times. Confirms `issue-transition` correctly removes the other
three canonical status labels (`planned`, `in-progress`, and whichever of
`needs-review`/`done` isn't the target) and adds only the target's mapped
label, per the `CANONICAL_STATUSES` loop in `tracker_ops.sh`. The unrelated
`duplicate` label (not a canonical status) was correctly left untouched.

### `duplicate-mark` — PASS (last mutating test on #596, as it closes the issue)

Used real closed issue **#558** (`security(ci): workflow shell injection risk
in release.yml`) as the `--duplicate-of` target purely to exercise the
comment/label/close mechanics — no semantic claim that #596 is an actual
duplicate of #558 (#596 is a throwaway test issue with no real duplicate).

```
$ configs/claude/scripts/tracker_ops.sh --provider github duplicate-mark 596 --duplicate-of 558
https://github.com/RB-chrismandich/Manifest/issues/596#issuecomment-5006986709
https://github.com/RB-chrismandich/Manifest/issues/596
✓ Closed issue RB-chrismandich/Manifest#596 ([test-tracker-ops] contract matrix scratch issue (Task 12))

$ gh issue view 596 --json state,labels,comments \
    -q '{state:.state, labels:[.labels[].name], comment_count:(.comments|length), last_comment:.comments[-1].body}'
{"comment_count":2,"labels":["duplicate","done"],"last_comment":"Duplicate of #558","state":"CLOSED"}
```
Exit 0. All three steps of the github duplicate-mark mapping (comment "Duplicate
of #M" + `duplicate` label + close) confirmed via a fresh `gh` read.

### `sub-issue-create` / `sub-issue-list` — N/A, documented gap (expected)

```
$ configs/claude/scripts/tracker_ops.sh --provider github sub-issue-create 596 --title "sub"
tracker-ops: sub-issue-create not implemented for github (registry documents the mapping; see spec §4.1)
[exit 4]

$ configs/claude/scripts/tracker_ops.sh --provider github sub-issue-list 596
tracker-ops: sub-issue-list not implemented for github (registry documents the mapping; see spec §4.1)
[exit 4]
```
Exit 4 both times — this is the documented, correct behavior (github has no
native sub-issue verb wired into `tracker_ops.sh`; see `tracker_providers.yml`
tier_map comment and spec §4.1), not a failure.

### `issue-close` — PASS (dedicated direct-invocation evidence)

`duplicate-mark` already exercises `issue-close` internally (same code path),
but a dedicated scratch issue (#597) was created and closed to get direct-verb
evidence rather than relying solely on an indirect call:

```
$ configs/claude/scripts/tracker_ops.sh --provider github issue-create \
    --title "[test-tracker-ops] issue-close direct-verb scratch (Task 12)" --body "..."
https://github.com/RB-chrismandich/Manifest/issues/597

$ configs/claude/scripts/tracker_ops.sh --provider github issue-close 597
✓ Closed issue RB-chrismandich/Manifest#597 ([test-tracker-ops] issue-close direct-verb scratch (Task 12))

$ gh issue view 597 --json state -q '.state'
CLOSED
```
Exit 0.

## Cleanup confirmation

```
$ gh issue view 596 --json number,state,title -q '"#\(.number) [\(.state)] \(.title)"'
#596 [CLOSED] [test-tracker-ops] contract matrix scratch issue (Task 12)
$ gh issue view 597 --json number,state,title -q '"#\(.number) [\(.state)] \(.title)"'
#597 [CLOSED] [test-tracker-ops] issue-close direct-verb scratch (Task 12)
```

Both scratch issues end the run **CLOSED**. No labels were created or deleted
solely for this test — every label touched (`duplicate`, `needs-review`,
`done`) already exists in `configs/claude/config/labels.yml` / the repo's
provisioned label set and was left in place (removing them would be
regressing shared registry state, not test cleanup).

## Bugs found

None. Every github operation behaved exactly per the `tracker_ops.sh` /
`git_ops.sh` routing logic and the `tracker_providers.yml` mapping comments —
no fix was required.

## How to complete this matrix (gitlab / linear / jira)

Whoever runs the remaining three columns needs, per provider:

- **gitlab**: the `glab` CLI installed and authenticated (`glab auth login`)
  against a real GitLab project with the same label set provisioned (run
  `configs/claude/scripts/label_sync.sh` against it first, or confirm labels
  already exist). Repeat the same operation list with
  `tracker_ops.sh --provider gitlab`; `git_ops.sh`'s gitlab branch already
  translates `--add-label`/`--remove-label` to `--label`/`--unlabel` and
  `issue-comment` to `glab issue note`.
- **linear**: a `LINEAR_API_KEY` environment variable (or a token at
  `~/.config/linear/token`, whichever `linear_ops.sh` reads — check its
  auth-resolution order before running) against a real Linear team/workspace.
  Linear's `issue-label` verb is *expected* to exit 4 (not implemented — see
  `tracker_ops.sh`'s explicit linear branch under the `issue-label` case,
  labels are status-transition-only there), and `duplicate-mark` routes to
  `issue-mark-duplicate` (a native state) rather than github's
  comment+label+close simulation — do not expect the same evidence shape.
  `sub-issue-create`/`sub-issue-list` ARE implemented for linear (via
  `create-sub-issue`/`list-sub-issues`) and should PASS, not N/A.
- **jira**: an active Atlassian MCP connection in the running agent context
  (jira is MCP-only per `tracker_providers.yml providers.jira.access`; running
  `tracker_ops.sh --provider jira <verb>` outside an agent/MCP context will
  correctly exit 3 — "unsupported-in-context" — that is not a failure, it's
  the documented boundary). The live test instead needs to invoke the
  `mcp_tools` listed in the registry (`getJiraIssue`, `createJiraIssue`,
  `addCommentToJiraIssue`, `getTransitionsForJiraIssue` +
  `transitionJiraIssue`, etc.) directly from an MCP-enabled agent session
  against a real Jira project, and cross-check against the same canonical
  operation list.

After each column is run, flip that provider's `verified: true` in
`configs/claude/config/tracker_providers.yml` and update this matrix's table
and evidence sections in place (same file, don't fork a new dated doc) — keep
one canonical contract matrix rather than one per provider.
