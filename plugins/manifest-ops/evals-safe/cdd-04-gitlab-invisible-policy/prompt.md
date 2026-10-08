---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
This is a GitLab Ultimate project owned by a group. A failing `policy-lint` job reports eslint `max-len: 80`, but the repository's compiled config shows neither that job nor an eslint command, and the checked-in eslint rule uses a different limit. Explain the likely source of the job, how to locate its configuration, and how to reconcile policy without assuming the job is a repository-defined lint step.
