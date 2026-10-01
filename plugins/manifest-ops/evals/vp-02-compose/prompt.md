---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Save this exactly as `docker-compose.yaml` in the current directory:

```
services:
  cache:
    image: redis:latest
  proxy:
    image: nginx
    ports:
      - "80:80"
```

Then pin the images so deploys are reproducible.
