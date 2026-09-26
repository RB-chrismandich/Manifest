---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Our `auth` service (port 7000, no published ports) is on a network declared as:

```yaml
networks:
  shared_internal:
    external: true
```
in compose project `idp`. How do I hit `http://auth:7000/.well-known/openid-configuration` and also debug DNS if it doesn't resolve?
