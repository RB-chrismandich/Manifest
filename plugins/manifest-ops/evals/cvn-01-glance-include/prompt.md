---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted; you don't have the files.)

My Glance dashboard config splits pages into files:

```yaml
# config/glance.yml
pages:
  - $include: pages/home.yml
  - $include: pages/media.yml
```

`yamllint config/` is clean. After deploying (glanceapp/glance:v0.6.4, config mounted at /app/config, uses ${DOMAIN} in a few places), the Media page is missing and Home has fewer widgets than it should. How should I validate this config so problems like this are caught before deploy?
