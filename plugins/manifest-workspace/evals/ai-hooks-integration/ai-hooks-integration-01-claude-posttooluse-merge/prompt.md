---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
runs: 3
---
My project's Claude Code settings live in `./settings.json` in the current directory. It doesn't exist yet in this checkout, so first create it with exactly this content:

```json
{
  "permissions": {"allow": ["Bash(npm test:*)"]},
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "/opt/guard/block-rm.sh"}]}
    ]
  }
}
```

Then add a hook so that after Claude edits or writes any file, `/opt/fmt/prettier-hook.sh` runs on it. Update `./settings.json` in place; don't lose anything that's already there.
