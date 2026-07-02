# Context Monitoring Guidance

**Purpose**: guidance for context-aware behavior in long sessions. There is no
automatic trigger — no hook or script consumes this template; the assistant (or
the user) invokes `/checkpoint` manually when the thresholds below are reached.

## Thresholds

- **80–95% context used**: run `/checkpoint` to compress the session into a
  scratchpad summary + memory updates before quality degrades.
- **Above 95%**: stop new work, run `/checkpoint`, and recommend starting a
  fresh session from the checkpoint.

## Suggested checkpoint message

```text
⚠️ CONTEXT CHECKPOINT RECOMMENDED

Usage: X/200000 (Y% used, Z% remaining)
Run /checkpoint to preserve session history before continuing.
```
