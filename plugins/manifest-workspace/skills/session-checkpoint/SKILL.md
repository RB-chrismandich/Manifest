---
name: session-checkpoint
description: Write a compact continuation checkpoint to XDG state when context is high, preserving decisions, progress, blockers, and verification evidence with integrity-checked durable continuity.
---

# Session Checkpoint

Use the adjacent `scripts/session_continuity.py` runtime and
`references/summary-template.md`. This extends the existing checkpoint flow; do
not create a second scratchpad or checkpoint store.

## Checkpoint flow

1. Read the original user goal and constraints from authoritative session state.
2. Inspect repository path, branch, HEAD, and `git status --short`; inventory
   every existing dirty-tree entry without modifying it.
3. Inspect every live operation. Record its owner, durable handle, current
   status, and monitoring obligation. If ownership cannot be verified, record
   the uncertainty and classify the boundary as `unknown`.
4. Fill the complete payload in `references/summary-template.md`. Evidence must
   include the exact verification command, outcome, and a durable checkpoint
   description; do not claim a check that was not run.
5. Run `session_continuity.py checkpoint --input <payload.json>`. Surface any
   validation, persistence, or integrity error. Never discard the active task
   because checkpointing failed.
6. Copy the emitted checkpoint path. The runtime writes it atomically with
   private permissions below `$XDG_STATE_HOME/manifest/checkpoints/`.

Do not copy secrets, full transcripts, or large raw command output.

## Compaction-aware reminder

Claude hooks record `PreCompact` attempts and count a compaction only after the
same primary session emits `SessionStart` with `source=compact`. Retries are
deduplicated and child-agent events are excluded. A `PreCompact` event alone
never increments the count.

The reminder threshold comes from
`MANIFEST_COMPACTION_REMINDER_THRESHOLD`; it must be a positive integer and
defaults to `2`. Two is an experimental policy value, not a model-quality
limit. See `references/telemetry.md` for each harness's evidence boundary.

At or above the threshold:

1. Finish the current atomic action. Do not terminate work or stop monitoring.
2. Classify the boundary as `safe` only when no action is in flight and every
   live operation has verified ownership and a continuation obligation.
3. Write and integrity-check the checkpoint before running
   `session_continuity.py recommend --session-id <id> --boundary <state>
   --checkpoint <path>`.
4. If recommended, show the checkpoint path and its copyable continuation goal
   once. The user starts a fresh session explicitly.

Use `session_continuity.py defer --session-id <id>` when the user defers. Do not
repeat the reminder during that session. Never automatically restart, end the
session, abandon monitoring, duplicate an action, or claim completion because
the threshold was reached.

## Continuation

Before trusting checkpoint claims, re-read current Git state and live-operation
ownership, then run `session_continuity.py verify` with those current snapshots.
Treat a digest failure as corruption. If `trusted` is false, report every Git
field or operation handle that changed and reconcile it before acting. Use the
checkpoint's `continuation_goal` as the copyable goal; its first action must be
the revalidation step.
