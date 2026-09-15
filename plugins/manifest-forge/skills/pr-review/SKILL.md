---
name: pr-review
description: Review all open pull/merge requests on the active platform (GitHub/GitLab), assess each for mergeability, checks, staleness, and whether still needed, and recommend a disposition (keep, merge, close, needs-rebase) per PR. Analysis-only — no mutations.
---

# Open Pull Request Review

Triage the entire open-PR queue in one pass so you can quickly see which PRs are
ready, which are stale or superseded, and which need work. Reuses the repo's
platform abstraction (`git_platform.sh` / `git_ops.sh`).

This skill is backed by `../../runtime/bin/pr_review.sh`.

## When to use

- You want an overview of every open PR and a recommended action for each.
- Before a cleanup pass on the PR queue.
- To identify PRs that are no longer needed (already merged or superseded).

## Task

1. **Run the review** (analysis-only by default — it never merges or closes):

   ```bash
   # Triage every open PR on the auto-detected platform
   ../../runtime/bin/pr_review.sh

   # Custom staleness window + machine-readable output
   ../../runtime/bin/pr_review.sh --stale-days 14 --json

   # Force a platform
   ../../runtime/bin/pr_review.sh --platform gitlab
   ```

2. **Read the recommendations.** Each PR gets a disposition with a one-line
   rationale:
   - `merge` — mergeable, checks passing, not a draft.
   - `needs-rebase` — merge conflicts or failing checks.
   - `close` — branch already merged, or superseded by an earlier open PR on the
     same branch.
   - `keep` — active work (draft, pending checks, or simply ongoing).

3. **Act with confirmation.** This skill recommends; it does not change PRs. To
   act on a recommendation, use `git_ops.sh pr-merge` / the platform CLI
   explicitly, confirming each action with the user first.

## Notes

- **Analysis-only by default** (FR-014): no PR is merged, closed, or edited
  without an explicit, separate, confirmed action.
- **Empty queue** is reported cleanly; an **unauthenticated / missing CLI** is
  reported distinctly (not as a misleading "clean" result) so you know the
  difference between "no PRs" and "couldn't look".
- Platform commands resolve through `gh` or `glab` on `PATH`; authentication is
  owned by those native CLIs.

## Sub-agent dispatch

This skill uses the shared OMP dispatch contract in
`../../runtime/references/sub-agent-dispatch.md`: submit all ready independent
units in one `task` call, in waves of at most 32; children execute directly and
never redispatch; use `hub` only to coordinate or wait; and the parent validates
and aggregates evidence. If `task` is unavailable, work inline and report
`DEGRADED`.

When ≥3 open PRs exist, dispatch one independent read-only `reviewer` unit per
PR in one OMP `task` call (waves of at most 32); below that, review inline.
Each child assesses only its assigned PR and never redispatches. The parent
uses `hub` only to coordinate or wait, validates the returned evidence, and
assigns the final disposition directly—there is no text-consensus or synthesis
step. If `task` is unavailable, review inline and report `DEGRADED`; never fall
back to a provider CLI.
