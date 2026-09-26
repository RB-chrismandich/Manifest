---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Our compose checker flags DC-007 (run as non-root) on our `migrate` service, which genuinely has to run as root to chown the data volume once. How do I suppress just that finding without hiding anything else?
