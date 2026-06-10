---
name: address-pr-review-comments
description: Use when a PR has inline/bot review comments (Copilot, reviewers) to triage and resolve systematically — fetch via gh api, fix each, re-test, push, and reply.
---
# Address PR Review Comments

A repeatable loop for resolving review feedback on your own open PR. Recurs every time a PR comes back with inline comments.

1. **Fetch all comments, not just the summary.** Inline review comments don't show in `gh pr view`. Pull them explicitly:
   - `gh api repos/<owner>/<repo>/pulls/<N>/comments` (inline code comments)
   - `gh api repos/<owner>/<repo>/pulls/<N>/reviews` (review bodies)
   - `gh pr view <N> --comments` (issue-level discussion)
   Parse path + line + body for each so you know exactly what to change.
2. **Triage into SHOULD FIX vs CONSIDER.** Separate real correctness/security bugs from style/optional suggestions. Present the table to the user before mass-editing if the count is high or any are debatable.
3. **Read each target section before editing** — the comment line numbers may have drifted. Confirm the actual code matches the complaint (a flagged "always returns X" may already be partly fixed).
4. **Fix every accepted finding**, grouping related edits. Watch for fixes that invalidate existing tests (e.g. changing a data source a test seeds) — update those tests in the same pass.
5. **Re-run the full suite + lint on changed files** before committing. Never push a review fix on the strength of "it looks right."
6. **Commit with a message that enumerates each fix**, push, then **post one summary comment** mapping each review point → the fix (file:line + one-line description). Reply-to-thread APIs often 404; a single summary comment on the PR is the reliable channel.
7. If the host supports it, mark threads resolved; otherwise the summary comment closes the loop.
