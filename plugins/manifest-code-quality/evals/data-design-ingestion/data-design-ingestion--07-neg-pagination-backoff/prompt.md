---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I'm fetching a paginated REST API (`GET /awards?page=N`) and every so often a page
request comes back with a 500 or times out, so I silently lose that page's records
today. I'm not asking about how to store the data — the table design is already
settled. How should I add retries/backoff to the fetch loop itself so a transient
failure on one page doesn't drop records?
