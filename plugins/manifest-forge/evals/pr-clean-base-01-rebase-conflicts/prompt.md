---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
My PR #214 (feat/export) was cut from feat/auth by mistake. Rebasing onto main blows up:

```
$ git log --oneline origin/main..HEAD
f00d001 feat(export): add csv writer        <- mine
f00d002 feat(export): wire endpoint          <- mine
ab12cd3 feat(auth): session refresh          <- from feat/auth (not merged)
ab12cd4 feat(auth): token rotation           <- from feat/auth (not merged)
$ git rebase origin/main
CONFLICT (content): Merge conflict in src/auth/session.ts
```

How do I fix this PR?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
