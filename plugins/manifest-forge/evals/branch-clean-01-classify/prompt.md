---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
My local branch list is a mess. Which branches are safe to delete, and how do I delete them?

```
$ git branch -vv
  feat/login        3a1f2c9 [origin/feat/login: gone] add login form
  feat/search       8b7d6e5 [origin/feat/search] wip search
* feat/billing      1c2d3e4 [origin/feat/billing: ahead 2] billing api
  fix/typo          9f8e7d6 [origin/fix/typo: gone] fix readme typo
  main              0a0b0c0 [origin/main] Merge PR #120
  release/2.1       5e5e5e5 [origin/release/2.1] release 2.1
  spike/graphql     7a7a7a7 graphql spike (last commit 2025-11-02)
$ git branch --merged main
  fix/typo
  main
  release/2.1
```
Today is 2026-09-26.

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
