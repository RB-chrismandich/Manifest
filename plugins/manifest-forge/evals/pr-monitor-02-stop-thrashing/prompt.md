---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
The `integration` check on PR #201 has now failed 3 times in a row after three different fix attempts. The log ends with `ECONNREFUSED 10.0.3.12:5432` in the CI runner. Should I keep trying fixes?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
