---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
I tried to list review threads and got:

```
$ gh pr view 122 --json reviewThreads
Unknown JSON field: "reviewThreads"
```

How do I get every review thread (there are >100 comments) with their resolved state?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
