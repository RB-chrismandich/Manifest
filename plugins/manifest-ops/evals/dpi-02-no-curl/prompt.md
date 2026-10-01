---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Compose project `shop`, service `api` (built `FROM python:3.12-slim`, listens on 8000, network `internal`, no published ports). I tried `docker compose exec api curl http://localhost:8000/health` and got `curl: not found`. How do I probe it?
