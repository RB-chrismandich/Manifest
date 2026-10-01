---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, "Bash(python3:*)"]
model: sonnet
runs: 3
---
Write a production `docker-compose.yaml` for a Django app (gunicorn, image `ghcr.io/acme/portal:2.8.1`), Postgres 16, and Redis 7. Save it in the current directory.
