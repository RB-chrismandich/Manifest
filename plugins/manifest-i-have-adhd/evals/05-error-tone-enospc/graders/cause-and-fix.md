---
type: llm
focus: last_message
weight: 1
---
Score PASS only if ALL hold:
1. The first line is an action (e.g. a `docker system prune`/`docker builder prune` command or freeing disk), not sympathy or background.
2. It states the cause plainly (the runner's disk / Docker storage is full).
3. The tone is matter-of-fact: no alarm or apology phrasing.
4. It ends with one concrete next action (e.g. rerun the job, check `df -h`).
Otherwise FAIL.
