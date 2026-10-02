---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Our CI checks `prometheus.yml` and `rules/*.yml` with yamllint only. A bad alert rule still reached prod last week. What check should we add? We deploy prom/prometheus:v2.54.1.
