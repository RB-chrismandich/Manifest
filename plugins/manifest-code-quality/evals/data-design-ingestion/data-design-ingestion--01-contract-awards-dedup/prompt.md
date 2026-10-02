---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I'm building a nightly job that pulls newly awarded federal contracts from a public
contracts API into a local SQLite table for an internal dashboard. Once a contract
award is posted, it's final and never changes — the API only adds new awards over
time. To be safe against pagination lag, the nightly job always re-fetches a rolling
7-day window instead of just "since last run."

How should I design the table and write logic so that overlapping re-fetches of the
same window don't create duplicate award rows?
