---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
Treat `./data` in the current directory as my `XDG_DATA_HOME` (export `XDG_DATA_HOME="$PWD/data"` for anything you run). An older tool left my Manifest knowledge store corrupted. First create `./data/manifest/knowledge/entries.jsonl` containing exactly this one (truncated) line:

```
{"id": "KB-001", "category": "antip
```

Then capture a new lesson: python, antipattern, "mutable default arguments are shared across calls; default to None and allocate inside the function".
