---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
The GitHub Actions run `9912345678` is still running. Its `lint-and-generate` job has failed, but `gh run view ... --log-failed` says logs will only be available after completion; another end-to-end job will take about 40 minutes. How can I identify the failed step and reproduce it before the whole run ends?
