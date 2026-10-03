---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
I ran `git branch -d feat/login` and got:

```
error: The branch 'feat/login' is not fully merged.
If you are sure you want to delete it, run 'git branch -D feat/login'.
```

The remote for it says [gone]. Should I just -D it? Also should I clean up the remote branches too?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
