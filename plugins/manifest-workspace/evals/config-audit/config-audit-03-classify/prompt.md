---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Create `./state/manifest/installation.json` with exactly:

```json
{"harnesses": {"cursor": {"plugins": ["manifest-forge@manifest"], "capabilities": {"skills": "generated", "hooks": "unsupported", "agents": "degraded"}}}}
```

Audit the Cursor harness's Manifest configuration against that receipt. For each capability, give me its status. Only audit Cursor.
