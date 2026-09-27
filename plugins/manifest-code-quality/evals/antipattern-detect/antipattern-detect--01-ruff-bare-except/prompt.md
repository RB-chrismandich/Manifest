---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our ruff run just failed in CI. Can you look at this and tell me whether it's a recurring pattern worth tracking?

```
$ ruff check .
src/api/users.py:42:5: E722 do not use bare `except`
src/api/orders.py:18:5: E722 do not use bare `except`
src/api/payments.py:77:5: E722 do not use bare `except`
Found 3 errors.
Error: ruff check exited with code 1
```

Just give me the analysis and the knowledge-base entry you would record (category, mechanism, detection cue, prevention rule). Don't try to save it anywhere — the knowledge base isn't available in this environment.
