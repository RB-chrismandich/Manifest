---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Write the iptables rules so only 10.0.0.5 can reach my Postgres container, which is published with `-p 5432:5432` on an Ubuntu Docker host.
