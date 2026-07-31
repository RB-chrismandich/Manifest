---
name: pr-address-comments
description: "Use when your open PR receives review feedback (inline comments, Copilot/CodeRabbit, review-body, issue discussion) — resolve every item truthfully: fix real issues, decline wrong ones with evidence, never mark resolved without a verified fix. Distinct from analysis-only pr-review."
---

# Address PR Review Comments

Resolve *every* piece of review feedback on your own PR truthfully: fix real
issues, decline wrong ones with evidence, and never mark a thread resolved
without a verified fix. Ignore non-actionable service notices
(usage-limit/bot-connector messages).

1. **Fetch all three feedback channels** — no single view is complete:
   - Inline code comments: `~/.claude/scripts/git_ops.sh pr-comments N` —
     returns JSON `[{id, author, path, line, body}]` on both github and
     gitlab (github: PR review comments; gitlab: MR discussion notes with a
     diff `position`, i.e. genuinely inline comments only — general
     MR-level discussion notes and system notes are excluded).
   - Review bodies: `gh pr view <N> --json reviews,reviewThreads`
     (github-only — GitLab has no separate review-body concept, but its
     top-level (non-inline) discussion notes are NOT covered by
     `pr-comments` above; see "Issue-level discussion" below for how to
     fetch those on gitlab).
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
   accepted items; "Declining: {rationale + evidence}" for rejected ones,
   posted via `~/.claude/scripts/git_ops.sh pr-comment N "..."`. Then post one
   summary disposition table (comment → verdict → action/fix at file:line) on
   the PR so a reviewer can verify at a glance.

## Inline comment threads

- `~/.claude/scripts/git_ops.sh pr-comments N` already returns exact targets
  as `{id, author, path, line, body}` — no manual `--jq` parsing needed.
- Reply per item as a top-level comment (per-comment threaded replies often
  404 on both hosts): `~/.claude/scripts/git_ops.sh pr-comment N "Fixed in
  <commit>: ..."` / `"Declining: <rationale>"`. The step-8 summary disposition
  table is the reliable fallback channel regardless — post it either way.
- **github-only: thread resolution** — GitHub supports formally resolving a
  review thread; GitLab (via `glab`) has no equivalent, so this block is
  provider-conditional:
  - github: `gh api graphql -f query='mutation { resolveReviewThread(input:
    {threadId: "<thread_id>"}) { thread { isResolved } } }'`
    (thread IDs come from `gh pr view <N> --json reviewThreads`, *not* from
    `pr-comments`' `id` field — those are comment IDs, not thread IDs).
  - gitlab: no thread-resolve verb exists, so instead post
    `~/.claude/scripts/git_ops.sh pr-comment N "Resolved: <summary>"` to close
    the loop (routes to `glab mr note` under git_ops.sh).

## Review bodies

- **github-only**: review summaries arrive separately from inline threads
  (`gh pr view <N> --json reviews,reviewThreads`); extract each actionable
  point as its own triage item — they often restate or extend the inline
  comments.
- gitlab: no separate review-body concept, but note that `pr-comments` above
  is now inline-only (matching github) — general, non-inline MR discussion
  notes are NOT returned by it; fetch those separately in the step below.

## Issue-level discussion

- Top-level PR comments (`gh pr view <N> --comments`) can contain feedback
  too; triage them like any other item, and this thread is where the summary
  disposition table belongs.
- gitlab has no equivalent git_ops.sh verb for general MR discussion notes;
  fetch them directly: `glab api projects/:id/merge_requests/N/notes --jq
  '[.[] | select(.system == false)]'` (the Notes API — separate from
  `pr-comments`' Discussions-API-backed inline results).

> Absorbed: address-pr-review-comments, address-review-comments (2026-06)
