---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill]
runs: 3
model: sonnet
---
I'm about to write a nightly script that shells out to `agy -p` to summarize the day's Sentry issues before posting to Slack. The Sentry export can be a few hundred KB some days. What's the right way to structure the call so it doesn't blow up on big days, and so I can write CI tests for it without hitting the real agy CLI or network?
