---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
In the `checks` job, the generated-file verification step failed and the later unit-test step was skipped; tests pass on my current checkout. Diagnose what this result means and give a reliable local reproduction and corrective procedure.
