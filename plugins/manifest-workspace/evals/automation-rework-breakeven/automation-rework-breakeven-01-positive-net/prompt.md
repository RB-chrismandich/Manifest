---
max_turns: 8
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Our code-review skill v1 averages 12,000 tokens per run; v2 averages 18,000 and finds more issues. We run it about 1,000 times a month. From our evals, v1 misses something that later needs a cleanup session in about 20% of runs, while v2 needed no cleanup on those same evals. We measured a cleanup session at ~40,000 tokens on average (3 recovery runs, 36k–44k). Is v2 worth switching to? Give me the numbers.
