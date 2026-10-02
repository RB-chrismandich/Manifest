---
max_turns: 4
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
On a plain Ubuntu server (no Docker installed), give me iptables rules that allow SSH only from 10.0.0.0/8 and drop it from everywhere else.
