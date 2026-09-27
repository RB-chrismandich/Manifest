---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill]
runs: 3
---
We're adding a Slack notifier to our health-check suite. If `SLACK_WEBHOOK_URL` isn't set in a given environment, what should the check function do? Right now the plan is just to `return true` and move on so the rest of the suite doesn't fail.
