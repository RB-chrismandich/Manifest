---
max_turns: 12
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep, Write]
runs: 3
---
Write me an OpenCode plugin (using the exported-function API: a plugin function that returns an object of hook handlers such as `"tool.execute.before"`) that appends a line to `/tmp/opencode-bash.log` every time OpenCode is about to run its bash tool, containing the command. Save it as `./audit-bash.js` in the current directory.
