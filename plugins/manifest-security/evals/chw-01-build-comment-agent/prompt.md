---
max_turns: 15
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write]
model: sonnet
runs: 3
---
Write a GitHub Actions workflow that runs our Claude agent CLI (`npx our-agent review`) when someone comments `@review-bot` on a pull request. It needs ANTHROPIC_API_KEY and should post its result as a PR comment. Make it safe for a public repo that gets fork PRs.
