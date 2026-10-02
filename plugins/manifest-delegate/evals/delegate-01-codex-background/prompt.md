---
max_turns: 25
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Bash, Write]
runs: 3
---
Use the delegate plugin to hand this to codex in the background and give me the job id so I can check on it later: "Read this repository and write a one-paragraph summary of its architecture." Don't let it modify anything.
