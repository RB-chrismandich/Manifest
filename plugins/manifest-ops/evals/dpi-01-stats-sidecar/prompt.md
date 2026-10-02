---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
My compose project is named `homelab`. It has:

```yaml
services:
  controld-stats:
    image: ghcr.io/acme/controld-stats:0.3.1
    networks: [backend]
networks:
  backend: {}
```

No ports are published. `curl localhost:8080/summary` from the host fails with connection refused. How do I check that `/summary` actually returns data?
