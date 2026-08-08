---
name: session-checkpoint
description: Write a compact continuation checkpoint to XDG state when context is high, preserving decisions, progress, blockers, and verification evidence.
---

# Session Checkpoint

Write checkpoints below `$XDG_STATE_HOME/manifest/checkpoints/` using the
adjacent `references/summary-template.md`. Include objective, constraints,
completed work, current tree state, tests run with outcomes, unresolved
findings, and the next concrete action.

Do not copy secrets, full transcripts, or large command output. Checkpoint
failure must be surfaced but does not rewrite or discard the active task.
