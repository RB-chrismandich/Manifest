---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Our compose checker reports:

```
docker-compose.yaml:14  DC-005 high [db] stateful service reachable from the public tier
```
Our file has `web` (ports 443:8443) and `db` (postgres) with no `networks:` defined. What does this mean and how do I fix it without breaking the app?
