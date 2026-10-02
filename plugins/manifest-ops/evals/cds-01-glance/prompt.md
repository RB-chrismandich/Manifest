---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from my server; you don't have the files.)

`docker-compose.yml`:
```yaml
services:
  glance:
    image: glanceapp/glance:v0.6.4
    volumes:
      - ./config:/app/config:ro
    environment:
      TZ: ${TZ}
    ports: ["8080:8080"]
```

`.env` (next to the compose file):
```
TZ=America/Denver
DOMAIN=home.example.net
GITHUB_TOKEN=ghp_xxx
```

`config/glance.yml` excerpt:
```yaml
server:
  base-url: https://${DOMAIN}
pages:
  - name: Home
    columns:
      - widgets:
          - type: repository
            repository: acme/app
            token: ${GITHUB_TOKEN}
```

`docker compose config` is clean and the container starts, but it immediately exits with `environment variable DOMAIN not found`. The variable is right there in .env. What's wrong?
