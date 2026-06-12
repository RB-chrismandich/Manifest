---
name: address-pr-comments
description: >-
  Use when your own open PR receives review feedback — inline comments (human or
  bot like Copilot/CodeRabbit), review-body summaries, or issue-level discussion
  — to fetch via gh api, triage and verify each claim, fix, re-test, push, and
  reply to or resolve every item. Distinct from analysis-only pr-review.
---

# Address PR Review Comments

Resolve *every* piece of review feedback on your own PR truthfully: fix real
issues, decline wrong ones with evidence, and never mark a thread resolved
without a verified fix. Ignore non-actionable service notices
(usage-limit/bot-connector messages).

1. **Fetch all three feedback channels** — no single view is complete:
   - Inline code comments: `gh api repos/<owner>/<repo>/pulls/<N>/comments`
   - Review bodies: `gh api repos/<owner>/<repo>/pulls/<N>/reviews` (or `gh pr view <N> --json reviews,reviewThreads`)
   - Issue-level discussion: `gh pr view <N> --comments`
2. **Verify each claim against current code before acting**: open the exact
   file and lines cited and confirm the assertion (counts, staleness, logic)
   is actually true. Reviewers — especially bots — are sometimes wrong, and
   comment line numbers may have drifted since the review.
3. **Triage per item**: real bug or valid nit (SHOULD FIX) vs optional style
   (CONSIDER) vs wrong/not-applicable. Correct → plan a minimal, scoped fix.
   Wrong → gather counter-evidence (e.g. `ls -ld` proving a double-count, a
   grep count, a docs link). Present the triage table to the user before
   mass-editing if the count is high or any items are debatable.
4. **Look for related issues the review missed**: while fixing a flagged item,
   check whether your change introduced adjacent staleness (index dates,
   counts, cross-links). Bot-found classes worth checking carefully:
   falsy-vs-None checks (`if x` treating `0`/`0.0` as missing), float dedup
   keys missing `:.2f`, wall-clock vs domain-date staleness, denominator scope
   (all rows vs filtered subset), missing input `.strip()`/validation, and
   middleware that buffers streaming responses.
5. **Apply fixes, grouping related edits**: watch for fixes that invalidate
   existing tests and update those in the same pass; add or update a test for
   any behavioral fix so the comment can't regress.
6. **Re-run the full suite + lint (the same checks CI runs, e.g. markdownlint
   with CI's globs) before
   committing** — never push a review fix on the strength of "it looks right."
7. **Commit with a message that enumerates each fix and references the
   review**, push, and confirm CI green on the new run.
8. **Reply to every item — never leave one silent**: "Fixed in {commit}" for
   accepted items; "Declining: {rationale + evidence}" for rejected ones. Then
   post one summary disposition table (comment → verdict → action/fix at
   file:line) on the PR so a reviewer can verify at a glance.

## Inline comment threads

- Parse exact targets with `--jq '.[] | {id, path, line, body}'`.
- Reply per thread:
  `gh api repos/<owner>/<repo>/pulls/<N>/comments/<comment_id>/replies -X POST -f body="..."`
  (these reply endpoints often 404; when they do, the summary comment from
  step 8 is the reliable fallback channel — post it either way).
- If the host supports it, mark threads resolved; otherwise the summary
  comment closes the loop.

## Review bodies

- Review summaries arrive separately from inline threads (`/reviews` or
  `--json reviews`); extract each actionable point as its own triage item —
  they often restate or extend the inline comments.

## Issue-level discussion

- Top-level PR comments (`gh pr view <N> --comments`) can contain feedback
  too; triage them like any other item, and this thread is where the summary
  disposition table belongs.

> Absorbed: address-pr-review-comments, address-review-comments (2026-06)
