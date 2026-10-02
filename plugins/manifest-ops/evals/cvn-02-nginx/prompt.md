---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
I edited a couple of files in nginx `conf.d/` (we run nginx:1.27-alpine in Docker with `./conf.d` mounted to `/etc/nginx/conf.d`). How do I check the config before reloading prod?
