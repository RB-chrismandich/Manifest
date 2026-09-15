# Context Monitoring Guidance

This prompt is advisory. It does not restart sessions or invoke checkpoints.
The Claude plugin can confirm completed compactions through its paired lifecycle
hooks. Codex, Gemini, Cursor, Antigravity, Devin, and other harnesses without a
verified completion signal must report compaction telemetry as `unknown`.

## Policy

- Preserve state manually whenever context pressure, a user-requested handoff,
  or suspected state loss makes a checkpoint useful; do not invent a context
  percentage.
- At the configurable threshold (default: two confirmed Claude compactions),
  finish the current atomic action and wait for a verified safe boundary.
- Write and integrity-check a private checkpoint before recommending a fresh
  session once. Explicit deferral suppresses further reminders for that session.
- An active or unknown boundary is not safe. Continue the work or monitoring
  obligation until ownership and current state can be verified.
- Never auto-restart, terminate work, abandon monitoring, duplicate actions, or
  claim completion because a threshold was reached.

The default of two is an experimental operational value, not a model-quality
limit. Mandatory restart policy requires comparative evaluation evidence first.
