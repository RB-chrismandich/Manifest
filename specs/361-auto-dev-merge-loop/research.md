# Phase 0 Research — Autonomous PR Lifecycle & Merge Loop

All `gh` mechanics below were **verified live** against this repo (`gh 2.92.0`,
`ReefBytes-Owner/Manifest`) by parallel research agents. Read-only; no state mutated.

---

## R1. Admin-bypass merge + pre-flight admin-capability detection (FR-008, FR-009, FR-020)

**Decision**: Detect admin capability *before* attempting, then admin-merge; fail closed
otherwise.

```bash
owner_repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
is_admin=$(gh api "repos/${owner_repo}" --jq '.permissions.admin')   # "true" | "false"
# also probe branch protection (404 = no gate, plain merge ok):
gh api "repos/${owner_repo}/branches/main/protection" --jq \
  '{enforce_admins:.enforce_admins.enabled, required_signatures:.required_signatures.enabled}'
# fail closed if: is_admin != true  OR  enforce_admins == true  OR  required_signatures == true
gh pr merge "$PR" --squash --admin --delete-branch
```

**Rationale**: A bot author cannot self-supply a code-owner approval; the only sanctioned
bypass is admin merge, and `--admin` errors *at merge time* if the actor lacks admin — so the
loop must detect capability up front (`.permissions.admin`, one read-only GET) and fail closed
rather than discover it on a mid-loop failed merge.

**Alternatives considered**: `gh repo view --json viewerPermission` (== `ADMIN`) — equivalent
string-compare fallback. `gh api .../collaborators/{user}/permission` — needs the real login
and 404s on the wrong name (brittle for bots). GraphQL `viewerPermission` — heavier, no gain.

**Gotchas** (all verified):
- **`enforce_admins=true` → `--admin` cannot bypass even for an admin.** Hard stop.
- **`required_signatures=true` → unsigned admin merge rejected.** (Relevant: our signing agent
  has been wedging — the loop must sign or this blocks. On this repo `required_signatures=false`.)
- Live `main` protection here: `enforce_admins=false, require_code_owner=true,
  required_reviews=1, required_signatures=false` → admin merge **will** succeed.
- Bot **display-name ≠ login**: account shows `ReefBytes-Owner` but `gh api user -q .login` =
  `RB-chrismandich`. Prefer `.permissions.admin` (no username needed).
- Known gh bug: `--admin` does **not** reliably bypass a required **merge queue**
  ([cli#8746](https://github.com/cli/cli/issues/8746), [cli#8971](https://github.com/cli/cli/issues/8971))
  — detect a required merge queue separately and fail closed.
- Token scopes present: `gist, read:org, repo, workflow` — `repo` covers protection-read + admin merge.

**GitLab parity (design-only; `glab` not installed)**: `glab mr merge <n> --squash
--remove-source-branch`; capability is role-based (Maintainer+); pre-flight via
`glab api projects/:id --jq .permissions.project_access.access_level` (≥40).

---

## R2. Actionable-comment / review-state classification (FR-007a, SC-002)

**Decision**: Block the merge on **either** a human `CHANGES_REQUESTED` review **or** an
unresolved human review thread. Do not hard-block on bot threads.

```bash
# (a) human "request changes" — use latestReviews (current per-reviewer state, deduped)
gh pr view "$PR" --json latestReviews --jq \
  '[.latestReviews[] | select(.state=="CHANGES_REQUESTED"
     and (.authorAssociation|IN("OWNER","MEMBER","COLLABORATOR")))] | length'   # >0 → block

# (b) unresolved threads, split human vs bot — GraphQL ONLY (isResolved absent from REST/gh pr view)
gh api graphql -f query='
query($owner:String!,$repo:String!,$pr:Int!){ repository(owner:$owner,name:$repo){
  pullRequest(number:$pr){ reviewThreads(first:100){ nodes{
    isResolved isOutdated comments(first:1){ nodes{ author{ login __typename } authorAssociation body } } } } } } }' \
  -F owner=OWNER -F repo=REPO -F pr="$PR" \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved==false)]
        | {unresolved_human:([.[]|select(.comments.nodes[0].author.__typename=="User")]|length),
           unresolved_bot:  ([.[]|select(.comments.nodes[0].author.__typename=="Bot")]|length)}'
# gate: block on unresolved_human > 0; bot threads advisory
```

**Rationale**: `reviewThreads.isResolved` is **GraphQL-only**. `latestReviews` (not `reviews`)
gives current per-reviewer state so a later approval supersedes an earlier change-request.
`__typename == "Bot"` vs `"User"` is the authoritative bot discriminator.

**Alternatives considered**: `gh pr view --json reviews` (un-deduped history, strips `[bot]`
suffix, no type field — unusable for the gate). REST `/pulls/{n}/reviews` (has `user.type` but
still no thread `isResolved`; GraphQL gets all in one call).

**Gotchas** (verified):
- `reviewDecision` is `null` with no required reviewers, and `REVIEW_REQUIRED` ≠ a hard block by
  itself — combine with `latestReviews` + thread counts; handle `null` defensively.
- `[bot]` suffix is surface-dependent (GraphQL no-suffix, REST with-suffix) → classify on
  `__typename`/`type`, never the login string. Copilot=`Copilot`, CodeRabbit=`coderabbitai`.
- Outdated-but-unresolved threads are still `isResolved:false` — recommend gating on
  `isResolved` regardless of `isOutdated`.
- `gh api graphql` needs `-F pr=<n>` (typed Int), not `-f` (string → schema error).

---

## R3. PR check status + post-merge `main` CI health (FR-001, FR-012a, FR-017)

**Decision (a)** — classify a PR's checks, **pending ≠ failing**:

```bash
buckets=$(gh pr checks "$PR" --json bucket -q '.[].bucket' 2>/dev/null)
if   grep -qx fail <<<"$buckets" || grep -qx cancel <<<"$buckets"; then echo FAIL
elif grep -qx pending <<<"$buckets"; then echo PENDING
elif [ -z "$buckets" ]; then echo NO_CHECKS    # empty = no CI configured — distinct state!
else echo PASS; fi
# exit-code shortcut: gh pr checks <n> → 0=pass, 8=pending, 1=fail(overloaded), 4=auth
```

**Decision (b)** — `main` HEAD post-merge CI (halt-on-red detector). **Use the Checks API,
never the combined-status API** (the latter is blind to GitHub Actions):

```bash
SHA=$(gh api repos/{owner}/{repo}/commits/main -q '.sha')
gh api "repos/{owner}/{repo}/commits/$SHA/check-runs" -q '[.check_runs[]|.conclusion]'
# RED if any failure/cancelled/timed_out/action_required; running if any status!=completed
# (conclusion null); GREEN if all completed + success/skipped/neutral
```

**Rationale**: GitHub Actions report via `/check-runs`, not the legacy `/status` (verified live:
`/status` returned `state:pending, total_count:0` while all 3 Actions were `completed/success`).
`gh pr checks --json bucket` is the only field that pre-folds the heterogeneous
`CheckRun`(uses `status`/`conclusion`) vs `StatusContext`(uses `state`) schema split.

**Alternatives considered**: `gh pr checks --watch` — blocks with **no internal timeout**;
rejected for the loop (can hang on a never-scheduled check). If used, wrap in external
`timeout`. `statusCheckRollup` — usable but requires `__typename` branching; `bucket` is better.

**Gotchas**: NO_CHECKS (empty rollup, gh exits 1) must be a distinct state — not PASS, not FAIL
— else a no-CI PR silently auto-merges or stalls. Post-merge, GitHub re-runs CI on the new main
commit; poll until all `completed` before declaring main green/red. GitLab needs
`glab ci status --branch main` (branch on `git_platform.sh`).

---

## R4. Conflict update, concurrency guard, branch prune (FR-010, FR-011, FR-023)

**Decision (1) — one-attempt conflict update**: read merge-state JSON (authoritative), act on
`BEHIND`, re-read to confirm; treat `DIRTY`/`CONFLICTING` as hand-to-human. Do **not** trust
`update-branch`'s exit code as the oracle.

```bash
read_state(){ gh pr view "$1" --json mergeable,mergeStateStatus -q '.mergeable+" "+.mergeStateStatus'; }
for _ in 1 2 3 4 5; do set -- $(read_state "$PR"); [ "$1" != UNKNOWN ] && break; sleep 3; done
case "$1:$2" in
  CONFLICTING:*|*:DIRTY)            echo conflict→human; exit 2 ;;
  MERGEABLE:BEHIND)                 gh pr update-branch "$PR" || { echo update-failed→human; exit 2; } ;;
  MERGEABLE:CLEAN|MERGEABLE:HAS_HOOKS) : ;;          # ready
  *:BLOCKED|*:DRAFT|*:UNSTABLE)     echo "not ready ($2)→skip"; exit 3 ;;
esac
```
`mergeStateStatus`: `CLEAN`/`HAS_HOOKS`=ready, `BEHIND`=needs update (clean), `DIRTY`=conflict,
`BLOCKED`=protection unmet, `UNSTABLE`=non-required check pending, `DRAFT`, `UNKNOWN`=recomputing
(poll). `mergeable`: `MERGEABLE`/`CONFLICTING`/`UNKNOWN` (UNKNOWN = back off, not a conflict).
**One-attempt rule**: `update-branch` at most once/pass; if post-update re-read isn't
`MERGEABLE`/`CLEAN`, escalate — don't retry. Use default (merge) mode, **not `--rebase`**
(force-pushes/clobbers in a loop).

**Decision (2) — concurrency guard**: label-based lock `loop-active` (cross-machine visible) +
local `flock` lockfile (kills same-host races). Re-read after add to break TOCTOU; always
release in `trap … EXIT`; treat a `loop-active` older than N min as stale/reclaimable.

```bash
gh pr view "$PR" --json labels -q '.labels[].name' | grep -qx loop-active && { echo locked→skip; exit 0; }
gh pr edit "$PR" --add-label loop-active; sleep 1
[ "$(gh pr view "$PR" --json labels -q '[.labels[].name|select(.=="loop-active")]|length')" = 1 ] || { echo race→skip; exit 0; }
trap 'gh pr edit "$PR" --remove-label loop-active' EXIT
exec 9>"/tmp/prloop-${PR}.lock"; flock -n 9 || { echo local-lock→skip; exit 0; }
```
No gh-native mutex exists; a GitHub **merge queue** is the real native serializer but is out of
scope (branch-protection config). Auto-merge (`--auto`) serializes only the final merge, not the
loop's update/check phase.

**Decision (3) — branch prune**: `gh pr merge <n> --squash --delete-branch` deletes the **remote**
branch regardless of `deleteBranchOnMerge=false` (that setting governs only GitHub's *automatic*
deletion). When `$PWD` isn't a git repo, gh deletes the remote branch and only *skips the local*
step with a benign warning (fixed in cli/cli PR #4769, present in 2.92.0) — so the
"Skipped deleting the local branch" warning we saw earlier means remote cleanup succeeded.

**Gotchas**: only call `merge` after confirming `MERGEABLE`/`CLEAN` (older gh closed PRs on a
conflicting merge — cli#12773). `gh search prs` lacks `mergeStateStatus` (cli#13239) — must use
`gh pr view`. `--delete-branch` can leave a dangling local tracking ref (cli#7897/#8515) → run
`git fetch --prune`. Label add/remove emits timeline noise.

---

## R5. Self-pacing on the `/loop` harness + automation-author allowlist (from repo knowledge)

- **Self-pace vs ceiling (FR-017/017a)**: within a run, poll `gh pr checks` on a short cadence
  and act the instant the bucket is terminal; do not `--watch`-block. Bound the *whole run* by a
  hard ceiling (default 10 min). Because the agent prompt-cache TTL is ~5 min, prefer **short
  in-run polls then end the run** and let the next `/loop` invocation re-check, over one long
  blocking wait — ending the run early keeps the cache warm and the empty-run/in-flight
  accounting (FR-018a) drives re-entry. `ScheduleWakeup` cadence: short (≤270 s) while actively
  watching a pending pipeline; longer fallback when idle.
- **Automation-author allowlist (FR-013)**: a config list (e.g. `command_config.yml` or a small
  `automation_authors.yml`) of bot/automation logins (auto-dev account + Forge/Palette/Jules/
  Bolt/Copilot), matched against `gh pr view --json author -q .author.login`. Classify unknown
  authors as human → skip. Keep it config-driven so adding a bot needs no code change.

---

## Open items carried into Phase 1 / tasks

- Whether `merge_decision.sh decide` consumes the gate's `tier1.issues[]`/`tier2.concerns[]`
  arrays directly or a normalized projection (mirror #360's open item).
- Signing: an unsigned admin merge is fine on this repo (`required_signatures=false`), but the
  loop should detect a wedged signing agent and fail closed rather than emit unsigned merges if a
  repo ever requires signatures.
- Stale-lock reclaim window (N minutes) for `loop-active`.
