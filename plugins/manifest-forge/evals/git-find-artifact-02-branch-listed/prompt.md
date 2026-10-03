---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
I need docs/plans/promote-plan.md but it's not on my branch:

```
$ cat docs/plans/promote-plan.md
cat: docs/plans/promote-plan.md: No such file or directory
$ git branch -a
* feat/rollout
  main
  spec/promote
  remotes/origin/spec/promote
```

My working tree has uncommitted changes I don't want to disturb. How do I read that plan?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
