---
max_turns: 20
timeout_seconds: 480
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, "Bash(python3:*)"]
model: sonnet
runs: 3
---
Save this exactly as `docker-compose.yaml` in the current directory:

```yaml
services:
  web:
    image: ghcr.io/acme/shop-web:1.4.2
    ports:
      - "80:8000"
    environment:
      DATABASE_URL: postgres://shop:hunter2@db:5432/shop
    depends_on:
      - db
  db:
    image: postgres:latest
    environment:
      POSTGRES_USER: shop
      POSTGRES_PASSWORD: hunter2
    volumes:
      - ./pgdata:/var/lib/postgresql/data
```

Then review it for production readiness. Don't change the file; just tell me what's wrong, most important first.
