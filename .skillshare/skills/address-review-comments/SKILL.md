---
name: address-review-comments
description: Use when a bot (Copilot/CodeRabbit) or human leaves inline review comments on YOUR open PR and you need to fix, verify, push, and resolve each one. Mechanical gh-api workflow, distinct from analysis-only PR triage.
---
# Address Inline Review Comments on Your PR

Recurs on every PR that gets a bot review. The goal is to resolve *every* comment
truthfully: fix real issues, push, and reply with the resolving commit — never
mark resolved without a verified fix.

## Steps

1. **Fetch the inline comments** (the review-summary view omits them):
   `gh api repos/<owner>/<repo>/pulls/<N>/comments --jq '.[] | {id, path, line, body}'`
   Also check `gh pr view <N> --json reviews,comments` for top-level review text.
2. **Triage each comment** into: real bug, valid nit, or wrong/not-applicable.
   For each one you'll fix, read the cited file/lines first — don't fix blind.
3. **Group the fixes** and apply them. Common bot-found classes worth checking
   carefully: falsy-vs-None checks (`if x` treating `0`/`0.0` as missing),
   float dedup keys missing `:.2f` formatting, wall-clock vs domain-date for
   staleness, denominator scope (all rows vs filtered subset), missing input
   `.strip()`/validation, and middleware that buffers streaming responses.
4. **Run the full test suite + lint** after the fixes. Add or update a test for
   any behavioral fix so the comment can't regress.
5. **Commit referencing the review**, then push to the PR branch.
6. **Reply to each comment** with the resolving commit SHA and a one-line note:
   `gh api repos/<owner>/<repo>/pulls/<N>/comments/<comment_id>/replies -X POST -f body="..."`.
   If a comment was wrong, reply explaining why rather than silently ignoring it.
7. **Post a summary table** (comment → fix) on the PR thread so a reviewer can
   verify dispositions at a glance.
