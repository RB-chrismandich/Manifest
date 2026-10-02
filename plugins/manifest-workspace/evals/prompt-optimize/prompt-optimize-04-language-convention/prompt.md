---
max_turns: 6
timeout_seconds: 300
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Turn this into a skill template: "write a python script that rotates our app logs weekly and gzips the old ones". Context: every script in our repo is bash — our docs/CODING_STANDARDS.md says `.sh` is the canonical script language and we don't ship Python.
