---
max_turns: 25
timeout_seconds: 450
allowed_tools: [Skill, Read, Glob, Grep, Write, Bash]
runs: 3
---
Treat `./state` in the current directory as my `XDG_STATE_HOME` (export `XDG_STATE_HOME="$PWD/state"` for anything you run). Create `./state/manifest/installation.json` with exactly:

```json
{"harnesses": {"claude": {"plugins": ["manifest-code-quality@manifest", "manifest-docs@manifest", "manifest-ops@manifest", "manifest-security@manifest", "manifest-spec-planning@manifest", "manifest-workspace@manifest"]}, "codex": {"plugins": ["manifest-code-quality@manifest", "manifest-docs@manifest", "manifest-forge@manifest", "manifest-ops@manifest", "manifest-security@manifest", "manifest-spec-planning@manifest", "manifest-workspace@manifest", "stitch-design@manifest"]}}}
```

Then reconcile my Manifest plugin install: which harnesses have drifted, what's missing, and do I need a repair?
