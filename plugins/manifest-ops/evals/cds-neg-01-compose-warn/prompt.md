---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
`docker compose up` prints:

```
WARN[0000] The "DB_PASSWORD" variable is not set. Defaulting to a blank string.
```

and then postgres fails to init. My compose file has `POSTGRES_PASSWORD: ${DB_PASSWORD}`. Fix?
