---
name: address-pr-comments
description: Systematically fetch, adjudicate, fix, and reply to every inline review comment on your own PR, including declining wrong ones with evidence
---
# Address PR Review Comments

1. **Fetch everything**: `gh api repos/{owner}/{repo}/pulls/{pr}/comments` plus `gh pr view {pr} --json reviews,reviewThreads` — capture inline threads, review summaries, and top-level comments. Ignore non-actionable service notices (usage-limit/bot connector messages).
2. **Verify each claim against current code before acting**: open the exact file and line cited; confirm the reviewer's assertion (counts, staleness, logic) is actually true. Reviewers (especially bots like Copilot) are sometimes wrong.
3. **Adjudicate per thread**:
   - Correct → plan a minimal, scoped fix.
   - Wrong → gather counter-evidence (e.g. `ls -ld` proving a symlink was double-counted, a grep count, a docs link).
4. **Look for related issues the review missed**: while fixing a flagged item, check whether your own change introduced adjacent staleness (index dates, counts, cross-links) and fix those for internal consistency.
5. **Apply fixes, then validate locally**: run the same linters/tests CI runs (e.g. markdownlint on CI globs, unit tests) and confirm clean before pushing.
6. **Reply to every thread inline** — never leave one silent: "Fixed in {commit}" for accepted items; "Declining: {rationale + evidence}" for rejected ones.
7. **Push and confirm CI green**: push the fix commit, watch the new run, and report a disposition table (comment → verdict → action) once all checks pass.
