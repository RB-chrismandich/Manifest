---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
I have a Node script that fetches 12,000 SKUs one after another using axios with a keepAlive http.Agent. After ~20 minutes responses get slower and then it stalls entirely. If I run a fresh one-off script for the SKU it stalled on, it comes back instantly. What's the plan to get all 12k through?
