---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
A GitLab merge-request job named `test:integration` failed, but its UI log was truncated after exceeding the limit. Explain how to recover the job's effective configuration and reproduce its failure locally without making a larger log limit or rerun the main solution.
