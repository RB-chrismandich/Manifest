---
name: pr-merge-stacked
description: Use when merging stacked PRs/MRs via gh/glab — merge bottom-up, verify each child was auto-retargeted to the trunk (GitHub on parent-branch deletion, GitLab on merge), rebase the rest of the stack after a squash/rebase merge, and recover a child closed by deleting an unmerged parent's branch.
---
# Merge a Stacked PR Chain Safely

Distinct from `pr-clean-base` (rebasing one branch onto a fresh base) and `pr-reset-reapply` (untangling tangled
history). This is the merge-time choreography for an already-open stack.

**What the forge does for you.** GitHub: when a merged PR's head branch is deleted (`gh pr merge --delete-branch`,
the "Delete branch" button, or repo auto-delete), open PRs based on it are **retargeted** to the merged PR's base —
not closed (since 2020); the PR's issue events record `automatic_base_change_succeeded` or
`automatic_base_change_failed`. Keeping the branch means **no** retarget. GitLab: merging an MR into the default
branch updates the target of up to four open MRs that targeted it; deleting the source branch later retargets
nothing. Neither forge removes the merged parent's original commits from the children after a squash or rebase
merge — that is step 5.

If the repo uses GitHub's native stacked PRs (public preview), merge from the stack's merge box (or the asynchronous
merge API) instead: a merge lands every unmerged PR below it and rebases the next one onto the stack base; auto-merge
is not supported. Skip the steps below.

1. **Map the stack and pin its state.** List bottom → top with base and head, per PR:
   GitHub `gh pr view <n> --json number,baseRefName,headRefName,headRefOid`; GitLab `glab mr view <n> --output
   json` (`target_branch`, `source_branch`, `sha`). `TRUNK` is the **bottom** PR's base (`main`, `release/x`, …) —
   use it everywhere below, never a hard-coded `main`. Stop if the base chain is broken (some PR's base is not
   the PR below it). Record each branch's remote head now — the fetch keeps those commits available after the
   forge deletes branches, and the recorded table stays pre-rewrite until step 5 pushes. Keep it Bash 3.2-safe
   (the repo's shell floor): no `declare -A`, and store `branch SHA` pairs as whitespace-delimited words — a
   `branch=sha` encoding splits at the first `=`, which corrupts valid branch names containing `=` (e.g.
   `feature=api`). Keep the record in a fresh temp file **outside the worktree** — a tracked or leftover
   `.stack-rec` in the repo must never be truncated (step 9 removes the temp file):

   ```bash
   git fetch origin --prune
   STACK_REC=$(mktemp "${TMPDIR:-/tmp}/stack-rec.XXXXXX")
   for b in <bottom> … <top>; do printf '%s %s\n' "$b" "$(git rev-parse "origin/$b")" >> "$STACK_REC"; done
   ```

2. **Ensure CI gates every PR.** A workflow keyed `on: pull_request: branches: [main]` only runs for PRs targeting
   `main`; remove that filter so stacked children are tested too.
3. **Merge the bottom PR with a method the repo allows.** Check `gh repo view --json
   mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed` (GitLab: the project's merge method and squash
   option). Record the bottom branch's head as `PRE` = its `$STACK_REC` entry. **Gate the merge first:** required
   checks green and mergeable — `gh pr checks <n> --required --watch --fail-fast`, then `gh pr view <n> --json
   mergeable,mergeStateStatus` shows `mergeable` = `MERGEABLE` and `mergeStateStatus` `CLEAN` **or `HAS_HOOKS`**
   (repos with pre-receive hooks report `HAS_HOOKS` on an otherwise-mergeable PR; `merge_decision.sh` treats both as
   merge-ready); GitLab: the MR's own pipeline (`glab mr view <n> --output json` → `head_pipeline`) has `status`
   `success` and either `sha` equal to the MR's `sha` (branch/detached pipeline) or `source` =
   `merge_request_event` **with `source_sha` equal to the MR's current `sha`** (merged-results/merge-train
   pipelines run on a synthetic merge commit, so their `sha` never equals the MR's `sha`; `source_sha` carries
   the source head they tested — a leftover `head_pipeline` from before the last push shows the old `source_sha`
   and must be rejected). Read `head_pipeline`, not
   `glab ci status --branch` (branch pipeline), and confirm `detailed_merge_status` is `mergeable`. Then merge
   **exactly the commit you checked**: `gh pr merge <n> --merge|--squash|--rebase --delete-branch
   --match-head-commit "$PRE"`, or on GitLab `glab mr merge <n> [--squash] --sha "$PRE"` — a push after mapping
   makes the merge refuse instead of landing unreviewed commits. **GitLab rebase merges** cannot use that pin:
   `glab mr merge --rebase --sha` rebases first, then sends the stale pre-rebase SHA to the merge API and is
   rejected. Run them as `glab mr rebase <n>`, wait for `rebase_in_progress` false and read the new `sha`, verify
   the pipeline on that SHA per the gate above, then `glab mr merge <n> --sha <new-sha>` — keep the original `PRE`
   for step 5's fork-point. **Merge queue required:** `gh` rejects `--delete-branch`; run
   `gh pr merge <n> --match-head-commit "$PRE"` (it queues), wait for `state` = `MERGED`, then delete the branch
   (`gh api -X DELETE repos/{owner}/{repo}/git/refs/heads/<branch>` or the UI) unless auto-delete did.
4. **Verify the merge and the retarget — never assume them.**
   - Merged and landed: GitHub `gh pr view <n> --json state,mergeCommit` (`MERGED`); GitLab `state` = `merged`,
     using `squash_commit_sha`, else `merge_commit_sha`, else `sha` (fast-forward). Then `git fetch origin` and
     `git merge-base --is-ancestor <that-sha> origin/$TRUNK`.
   - Child's base: `gh pr view <child> --json baseRefName` / `glab mr view <child>` must show `$TRUNK`. Reason, if
     needed: `gh api --paginate repos/{owner}/{repo}/issues/<child>/events --jq '.[].event' | grep
     automatic_base_change` (issue events, not the timeline API). If it still targets the merged branch, retarget:
     `gh pr edit <child> --base $TRUNK` / `glab mr update <child> --target-branch $TRUNK`, and read it back.
5. **After a squash or rebase merge, rebase the remaining stack — as a bash script, not pasted into your shell**
   (it aborts on the first failure instead of pushing a half-rewritten stack, and never exits your terminal):

   ```bash
   #!/usr/bin/env bash   # STACK_REC=<file from step 1> land-stack.sh TRUNK PRE branch …   (stack bottom → top)
   set -euo pipefail
   trunk=$1 pre=$2; shift 2
   stack=("$@"); [ "${#stack[@]}" -ge 1 ] || { echo "no remaining branches" >&2; exit 2; }
   rec() { awk -v b="$1" '$1 == b {print $2}' "$STACK_REC"; }   # Bash 3.2 floor: no declare -A; branch SHA pairs
   git fetch origin --prune
   for b in "${stack[@]}"; do                                    # someone else moved a branch → stop, re-map
     [ "$(git rev-parse "origin/$b")" = "$(rec "$b")" ] || { echo "origin/$b moved — re-run step 1" >&2; exit 3; }
   done
   for b in "${stack[@]}"; do      # never discard local-only work
     git rev-parse -q --verify "refs/heads/$b" >/dev/null || continue
     git update-ref "refs/stack-backup/$b" "$b"                  # recoverable: git branch -f <b> refs/stack-backup/<b>
     # unpushed merge commits (git cherry ignores merges), or unpushed patches (rebased copies of remote ones are OK);
     # captured, not piped into grep -q — under pipefail an early-exiting grep makes git cherry die of SIGPIPE (141)
     merges=$(git rev-list --merges "origin/$b..$b"); unpushed=$(git cherry "origin/$b" "$b" | sed -n 's/^+ //p')
     if [ -n "$merges" ] || [ -n "$unpushed" ]; then
       echo "local $b has commits not on origin — push or move them, then re-run step 1" >&2; exit 4
     fi
   done
   if [ "$(git rev-list --count "origin/$trunk..$(git merge-base "origin/${stack[0]}" "$pre")")" -eq 0 ]; then
     echo "merge commit: nothing to drop"; exit 0                # only this script ends; continue at step 6
   fi
   for b in "${stack[@]}"; do                                    # a rebase would flatten merges in the stack
     [ -z "$(git rev-list --merges "origin/$trunk..origin/$b")" ] || {
       echo "origin/$b contains merge commits — rebase would drop them; land it by hand" >&2; exit 5; }
   done
   git switch --detach                                           # no stack branch may be checked out
   newbase="origin/$trunk" oldparent=$pre
   for b in "${stack[@]}"; do                                    # bottom → top
     git branch -f "$b" "origin/$b"                              # local = remote (checked above: nothing local-only)
     git rebase --onto "$newbase" "$(git merge-base "origin/$b" "$oldparent")" "$b"
     git switch --detach
     newbase=$b oldparent=$(rec "$b")                            # child forks from its parent's PRE-rewrite head
   done
   leases=(); refs=()
   for b in "${stack[@]}"; do leases+=("--force-with-lease=$b:$(rec "$b")"); refs+=("$b:$b"); done
   git push --atomic origin "${leases[@]}" "${refs[@]}"
   ```

   Afterwards re-record `$STACK_REC` from `origin` (step 1 — a fresh temp file). Why this shape: the fork point comes from the merged
   parent's head as recorded (`PRE`), so it is right even when the parent gained commits after the child branched;
   each branch is rebased onto its already-rewritten parent from that parent's **pre-rewrite** SHA, which also
   covers a middle branch that advanced after its own child branched (a single `--update-refs` rebase of the top
   branch would leave such a branch behind); every lease names the recorded SHA and the refspecs push nothing else.
6. **Make CI actually run against the new base.** A base change is a `pull_request` `edited` event, which GitHub
   Actions ignores by default (`opened`, `synchronize`, `reopened`). After a retarget with no push (merge-commit
   path), add `edited` to the workflow's `types:` or trigger a fresh run (empty commit, or close + reopen);
   re-running the old run reuses the old merge ref and does not count. Before merging the child, confirm a green
   run that started after the retarget: `gh pr checks <child>` or, on GitLab, the MR's `head_pipeline` (`glab mr
   view <child> --output json`) meeting the step-3 gate — `status` `success` and `sha` equal to the MR's current
   `sha`, or `source` `merge_request_event` **with `source_sha` equal to the MR's current `sha`** for
   merged-results/merge-train pipelines.
7. **Repeat 3–6** with the child as the new bottom and `PRE` = its `$STACK_REC` entry (re-recorded after any push).
8. **Recover a child closed by a deleted base.** Deleting the branch of a parent that was **closed without
   merging** (or any base deleted outside the merge flow) closes the PRs based on it; Reopen stays disabled while
   the base is gone. Restore it with `git push origin <recorded SHA>:refs/heads/<deleted-base>`, reopen
   (`gh pr reopen <child>` / `glab mr reopen <child>`), retarget to `$TRUNK`. If the abandoned parent's commits must
   not ship, run step 5's script with `PRE` = the parent's `$STACK_REC` SHA (skip step 4's merged-and-landed
   check). The restored base is a temporary remote ref that step 9's prune does not cover (it only handles merged
   branches): after the child's base reads back as `$TRUNK`, delete it with `git push origin --delete
   <deleted-base>`.
9. **Finish clean.** `git switch $TRUNK && git pull --ff-only`, prune merged branches, and remove the pinned
   record: `rm -f "$STACK_REC"`.
