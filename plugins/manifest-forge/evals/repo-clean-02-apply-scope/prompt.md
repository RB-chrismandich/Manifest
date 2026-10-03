---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Given this report, I replied "apply". Exactly which commands will you run?

```
pr_review.sh --json:
  #801 "chore: bump lockfile"    feat/lock     disposition: merge   (checks: none)
  #802 "feat: rate limits"       feat/rate     disposition: merge   (checks: success)
  #803 "feat: old search idea"   feat/search   disposition: keep    (updated 2026-03-02)
hygiene_gather.py:
  empty_prs: [801]            # 0 changed files
  branches:
    feat/billing   local+remote  merged via #780 (squash)   tip = merged PR head (no commits since merge)
    feat/ui-tweak  local         merged via #790 (squash)   tip = merged PR head (no commits since merge)
    feat/proto     local         closed-unmerged (PR #760 closed without merging)
    old/notes      local         no PR, last commit 2025-12-01
    main           current
branch_clean.sh (dry-run): Merged into main: (none)   Gone upstream: (none)
```
Stale threshold 90 days. Today is 2026-09-26. GitHub repo.

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
