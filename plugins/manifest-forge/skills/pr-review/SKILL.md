---
name: pr-review
description: Review all open pull/merge requests on the active platform (GitHub/GitLab), assess each for mergeability, checks, staleness, and whether still needed, and recommend a disposition (keep, merge, close, needs-rebase) per PR. Analysis-only — no mutations.
---

# Open Pull Request Review

Triage the entire open-PR queue in one pass so you can quickly see which PRs are
ready, which are stale or superseded, and which need work. Detect GitHub or
GitLab with `git_platform.sh`, then use that provider's native CLI.

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
   act on a recommendation, use `gh pr merge` or `glab mr merge` explicitly and
   confirm each action with the user first.

## Notes

- **Analysis-only by default** (FR-014): no PR is merged, closed, or edited
  without an explicit, separate, confirmed action.
- **Empty queue** is reported cleanly; an **unauthenticated / missing CLI** is
  reported distinctly (not as a misleading "clean" result) so you know the
  difference between "no PRs" and "couldn't look".
- Platform commands resolve through `gh` or `glab` on `PATH`; authentication is
  owned by those native CLIs.

## Sub-agent dispatch

Follow the [shared dispatch contract](../../runtime/references/sub-agent-dispatch.md).
When the configured threshold selects per-PR review, assign each reviewer one
read-only PR and make the final disposition directly from attributed evidence.
