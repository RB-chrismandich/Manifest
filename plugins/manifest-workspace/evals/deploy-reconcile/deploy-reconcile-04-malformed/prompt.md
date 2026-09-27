---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Create `./state/manifest/installation.json` containing exactly this (it got truncated during a crash):

```
{"harnesses": {"claude": {"plugins": ["manifest-forge@manifest",
```

Now check my Manifest plugin install for drift.
