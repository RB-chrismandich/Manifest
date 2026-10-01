---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
`kubectl rollout status deploy/api` is stuck at `Waiting for deployment "api" rollout to finish: 1 old replicas are pending termination...`. What do I check?
