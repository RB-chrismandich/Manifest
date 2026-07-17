# GitLab Forge-Verb Verification — `git_ops.sh` (Task 16)

> Documentation-level API verification for the 4 new GitLab twins added in
> Task 15's PR-cluster migration (`f1772b7`): `pr-reopen`, `pr-update-branch`,
> `repo-admin-check`, `commit-checks`. Companion to
> [2026-07-17-tracker-contract-matrix.md](2026-07-17-tracker-contract-matrix.md)
> (that doc covers `tracker_ops.sh` issue-tracker verbs across github/gitlab/
> linear/jira; this doc covers `git_ops.sh` PR/MR-forge verbs across
> github/gitlab only — different script, different abstraction, kept
> separate rather than merged into the tracker matrix). Plan:
> `docs/superpowers/plans/2026-07-16-agent-app-agnostic-skills.md`, Task 16.

## Scope note (deviation from the original plan text)

The original Task 16 plan text called for walking each documented sequence
against a **real scratch GitLab MR chain** using `glab`. That is not possible
in this environment: `command -v glab` fails (binary not installed), and no
GitLab project/credentials are available. Per the precedent set on Task 12
(live-test what's reachable, honestly mark what isn't — never fabricate a
pass), this pass is **documentation-level verification only**: each of the 4
verbs' GitLab API/CLI call was checked against GitLab's real, current public
docs (fetched live via WebFetch/WebSearch against `docs.gitlab.com`, not
recalled from training data). No `verified: true` flag is set anywhere — this
repo has no forge-verb-specific verified-flag config (only
`tracker_providers.yml`, which is Task 12's unrelated issue-tracker registry
and was not touched).

## Matrix

| Verb | GitLab call in `git_ops.sh` | Doc-level verdict | Evidence basis |
|---|---|---|---|
| `pr-reopen` | `glab mr reopen "$@"` | **CONFIRMED CORRECT** | External doc fetch: `docs.gitlab.com/cli/mr/reopen/` |
| `pr-update-branch` | `glab api projects/:id/merge_requests/:iid/rebase -X PUT` | **CONFIRMED CORRECT** (semantic-difference comment also accurate) | External doc fetch: GitLab Merge Requests API, "Rebase a merge request" section |
| `repo-admin-check` | `glab api projects/:id --jq '(...project_access\|group_access).access_level >= 40'` | **CONFIRMED CORRECT** (field names and the `>=40` threshold both match) | External doc fetch: GitLab Members API (access-level enum) + GitLab Projects API (`permissions.project_access`/`group_access` shape) |
| `commit-checks` | `glab api projects/:id/repository/commits/:sha/statuses --jq '[.[].status]'` | **CONFIRMED CORRECT** | External doc fetch: GitLab Commits API, "List the statuses of a commit" |

**All 4 verbs verified correct at the documentation level. No bugs found; no
code changes made to `git_ops.sh`.** All 4 remain genuinely un-live-tested
(no `glab` binary, no GitLab project) — see "Live-test instructions" below.

## Per-verb findings

### `pr-reopen` → `glab mr reopen <id>`

Fetched `https://docs.gitlab.com/cli/mr/reopen/` directly (this is glab's own
generated command-reference page, not a third party). Confirmed real,
current subcommand:

```
glab mr reopen [<id>... | <branch>...] [flags]
```

Matches the code's `glab mr reopen "$@"` call exactly — positional MR number,
no special flag translation needed (unlike `pr-close`, which needed a
`--comment` → `mr note` + `mr close` split in Task 15). This is also
consistent with the internal-convention signal noted in the task brief
(`mr close`/`mr merge` already exist and are used elsewhere in this file) —
but the claim here is **externally confirmed**, not just reasoned from
convention.

### `pr-update-branch` → `PUT projects/:id/merge_requests/:merge_request_iid/rebase`

Fetched the GitLab Merge Requests API doc (via `docs.gitlab.co.jp/ee/api/merge_requests.html`,
a GitLab-maintained regional mirror of the same content, after the primary
`docs.gitlab.com` anchor fetch truncated before reaching this section).
Confirmed:

- Method + path: `PUT /projects/:id/merge_requests/:merge_request_iid/rebase`
  — matches the code's `glab api "projects/:id/merge_requests/${mr_num}/rebase" -X PUT`
  exactly.
- **Response is `202 Accepted` with `{"rebase_in_progress": true, "merge_error": null}`
  — this is an asynchronous, fire-and-poll operation**, not a synchronous
  "branch is now updated" confirmation. This matters for correctness of the
  *caller*, not the verb itself: `pr_merge_loop.sh`'s only caller
  (`cmd_tick`'s `update-branch)` branch, line ~425) only checks the CLI's
  exit code (`gh_op update-branch "$pr" > /dev/null 2>&1 || apply_label ...`)
  and relies on the loop's next poll tick (`PR_MERGE_LOOP_POLL_SEC`, default
  30s) to observe the updated state — it never assumes completion from this
  call's return value. GitHub's own `update-branch` REST API is *also*
  asynchronous (202 Accepted, "Updating pull request branch" message), so
  the caller's fire-and-poll pattern is already correct for both platforms.
  **No bug** — but this async nature was not previously called out
  explicitly in `git_ops.sh`'s inline comment (which only notes the
  rebase-vs-merge semantic difference), so a maintainer reading only that
  comment might wrongly assume the gitlab call blocks until the rebase
  finishes. Left as-is (not a bug, not asked to expand the code comment) but
  flagged here in case Task 17+ wants to tighten it.
- The semantic-difference claim in the existing inline comment ("closest
  equivalent is a server-side rebase, semantically rebase not merge") is
  accurate — GitLab's rebase endpoint literally performs `git rebase`
  semantics on the source branch against the target, not a merge commit.

### `repo-admin-check` → `permissions.project_access.access_level` / `permissions.group_access.access_level`, threshold `>=40`

Two separate doc fetches:

1. GitLab Members API doc — confirmed the real access-level integer enum:
   No access=0, Minimal access=5, Guest=10, Planner=15, Reporter=20,
   Security Manager=25, **Developer=30, Maintainer=40, Owner=50**, Admin=60.
   The task brief's expected mapping (Guest=10, Reporter=20, Developer=30,
   Maintainer=40, Owner=50) matches exactly (the two extra tiers — Planner
   and Security Manager — are newer GitLab additions between Reporter and
   Developer/Security, and don't affect the `>=40` threshold).
2. GitLab Projects API doc (`Get a single project`) — confirmed the response
   shape literally contains:
   ```json
   "permissions": {
     "project_access": { "access_level": 10, "notification_level": 3 },
     "group_access": { "access_level": 50, "notification_level": 3 }
   }
   ```
   matching the code's `.permissions.project_access.access_level` /
   `.permissions.group_access.access_level` field paths exactly.

The code's `>= 40` threshold (Maintainer or Owner) is the correct doc-level
mapping for GitHub's `repo.permissions.admin` boolean — Maintainer is the
lowest GitLab role that can push to protected branches, manage most repo
settings, and bypass most restrictions, which is the closest single-role
analogue to GitHub's admin bit. **No bug.**

### `commit-checks` → `GET projects/:id/repository/commits/:sha/statuses`, filter `[.[].status]`

Fetched the GitLab Commits API doc, "List the statuses of a commit" section.
Confirmed:

- Path matches exactly: `GET /projects/:id/repository/commits/:sha/statuses`.
- Response is a **flat JSON array** of status objects (not wrapped in an
  envelope key) — the code's `--jq '[.[].status]'` (iterate the array
  directly) is structurally correct; it would be wrong if the response were
  wrapped (e.g. `{"statuses": [...]}`), but it is not.
- Each object's field is literally named `"status"` (not `"state"` or
  `"conclusion"`) with vocabulary exactly `pending`, `running`, `success`,
  `failed`, `canceled`, `skipped` — six values, single-`l` "canceled" (US
  spelling, unlike GitHub's double-`l` "cancelled").

Cross-checked against `pr_merge_loop.sh`'s caller-side comment
(`cmd_post_merge_check`, lines 311–314):

```
# NOTE: github check-run conclusions (failure/cancelled/timed_out/action_required)
# vs gitlab pipeline statuses (failed/canceled/...) use slightly different
# vocabulary; the grep below matches github's. This path only runs on github
# today (gitlab auto-merge fails closed before reaching post-merge-check).
```

This comment is **accurate**: real GitLab statuses (`failed`, `canceled`)
genuinely differ in spelling from GitHub's check-run conclusions (`failure`,
`cancelled`), and GitLab has no direct equivalent for GitHub's `timed_out` /
`action_required` conclusions. The comment also correctly notes this grep
pattern (`failure|cancelled|timed_out|action_required`) only runs on the
github code path today (gitlab's `repo-admin-check` fails closed before
`cmd_post_merge_check` would ever be reached with a gitlab `commit-checks`
result) — so the vocabulary mismatch is currently inert, not live, and
matches Task 15's own self-review on this exact point. **No bug — this is a
correctly-labeled known future gap, not a live defect.**

## Bugs found

None. All 4 verb implementations are correct against GitLab's real, current
public API/CLI surface. No changes were made to `git_ops.sh` or
`pr_merge_loop.sh`.

## Self-review — evidence basis per claim

| Claim | Evidence basis |
|---|---|
| `glab mr reopen` is a real, current subcommand with the shown syntax | External: fetched `docs.gitlab.com/cli/mr/reopen/` (glab's own generated reference) |
| `PUT .../merge_requests/:iid/rebase` is a real endpoint | External: fetched GitLab Merge Requests API docs (regional mirror, full anchor content) |
| Rebase endpoint is async (202 + `rebase_in_progress`/`merge_error`) | External: same fetch as above |
| `permissions.project_access.access_level` / `group_access.access_level` fields exist on the single-project response | External: fetched GitLab Projects API docs ("Get a single project") |
| Access-level integers (Guest=10 … Owner=50, Maintainer=40 threshold) | External: fetched GitLab Members API docs |
| `GET .../commits/:sha/statuses` returns a flat array with a `status` field and the 6-value vocabulary | External: fetched GitLab Commits API docs |
| `pr_merge_loop.sh`'s vocabulary-mismatch comment is accurate and the mismatch is currently inert | Internal: read `pr_merge_loop.sh` lines 297–322 and traced the gitlab `repo-admin-check` fail-closed path from Task 15's own report |
| `mr close`/`mr merge` conventions predicting `mr reopen` | Internal reasoning only, superseded by the external confirmation above — not relied on as the sole evidence |

No claim in this document rests on unconfirmed guessing from training-data
recall; every GitLab-doc-shape claim above was independently fetched live in
this session.

## Live-test instructions (for whoever gets real `glab` access)

### Setup

```bash
brew install glab   # or: go install gitlab.com/gitlab-org/cli/cmd/glab@latest
glab auth login      # against a real GitLab.com project or self-managed instance
cd <scratch-gitlab-repo-checkout>
```

Needs a scratch GitLab project you can push branches to, and (for
`repo-admin-check`) confirm your authenticated token/user has **at least
Maintainer** access on it — otherwise the verb will correctly report `false`
and that's not a bug, just not the interesting case to exercise.

### Suggested scratch MR chain sequence

Mirrors what `pr-merge-stacked` / `merge-stacked-pr-chain` actually do
(parent → child stacked chain, merge parent while retargeting child) plus
direct exercises of all 4 verbs Task 15 added:

1. **Build the chain**: `git checkout -b parent-branch`, commit, push;
   `git checkout -b child-branch` (based on `parent-branch`), commit, push.
   `glab mr create --source-branch parent-branch --target-branch main --title "parent"`,
   `glab mr create --source-branch child-branch --target-branch parent-branch --title "child"`.
2. **`commit-checks`** — push a commit to `child-branch` that triggers a
   pipeline (or push an empty commit if no CI is configured — the endpoint
   should still return `[]` or `null`, not error); run
   `configs/claude/scripts/git_ops.sh commit-checks <child-branch-head-sha>`
   and confirm it returns a JSON array of `status` strings from the real
   vocabulary (`pending`/`running`/`success`/`failed`/`canceled`/`skipped`).
3. **`repo-admin-check`** — run `configs/claude/scripts/git_ops.sh repo-admin-check`
   as a Maintainer/Owner (expect `true`) and, if a second lower-privilege
   token is available, as a Developer/Reporter (expect `false`).
4. **`pr-close` + `pr-reopen`** — close the child MR
   (`git_ops.sh pr-close <child-mr-iid> --comment "testing"`), confirm the
   note posted and the MR is closed via `glab mr view`, then
   `git_ops.sh pr-reopen <child-mr-iid>` and confirm it's open again via
   `glab mr view`.
5. **`pr-update-branch`** — push a new commit to `parent-branch` (or `main`)
   so `child-branch` is now behind its target, then
   `git_ops.sh pr-update-branch <child-mr-iid>`. Confirm the call returns
   `202`/succeeds, then **poll** `glab mr view <child-mr-iid> --output json`
   for `rebase_in_progress: false` and `merge_error: null` before asserting
   success (do not assert immediately — this is async, see finding above).
   Confirm `child-branch`'s HEAD now includes the new commit from its target
   (`git log --oneline child-branch` after fetching).
6. **Full stacked-merge exercise** — with the chain still in place, run
   through what `pr-merge-stacked`/`merge-stacked-pr-chain` document: merge
   the parent MR *keeping the branch* (`glab mr merge <parent-mr-iid>` without
   `--remove-source-branch`), retarget the child MR to `main`
   (`git_ops.sh pr-edit <child-mr-iid> --base main`, verify GitLab's
   `pr-edit` translation maps `--base` → `--target-branch`), confirm via
   `glab mr view <child-mr-iid>` that `target_branch` is now `main` and the
   MR is still open (not auto-closed), then delete the now-merged parent
   branch and clean up.
7. **Record results** in this doc's Matrix table (flip verdicts from
   "CONFIRMED CORRECT (doc-level)" to "LIVE-VERIFIED" with a dated evidence
   section, following the evidence-with-commands style of
   [2026-07-17-tracker-contract-matrix.md](2026-07-17-tracker-contract-matrix.md)'s
   github column) — do not simply flip a boolean flag with no transcript.

No `verified: true` config flag exists for `git_ops.sh` forge verbs to flip;
if one is introduced later, it must only be set after step 7's transcript
evidence exists, matching the same never-fabricate-green principle used in
the tracker contract matrix.
