# Compaction Telemetry and Enforcement Limits

| Harness | Completed-compaction evidence | Manifest behavior |
|---|---|---|
| Claude | A primary-session `PreCompact` followed by `SessionStart(source=compact)` for the same session | Count the unique completed sequence; deduplicate retries and exclude child agents |
| Codex | No verified completed-compaction event | Report `unknown`; manual checkpoint and advisory handoff only |
| Gemini | No verified completed-compaction event | Report `unknown`; manual checkpoint and advisory handoff only |
| Cursor | No verified completed-compaction event | Report `unknown`; manual checkpoint and advisory handoff only |
| Antigravity | No verified completed-compaction event | Report `unknown`; manual checkpoint and advisory handoff only |
| Devin | No verified completed-compaction event | Report `unknown`; manual checkpoint and advisory handoff only |
| Other harnesses | Unsupported until a completed-compaction lifecycle is verified | Report `unknown`; never infer zero or a count from tokens or transcript size |

Claude's `PreCompact` hook is evidence of an attempt, not completion. Manifest
pairs it with the post-compaction `SessionStart` signal and stores only
session-scoped continuity state. For unsupported harnesses, missing telemetry
must not block work or bypass existing safety gates.

Manifest's policy is advisory. It owns checkpoint validation and the Claude
plugin lifecycle adapter, but it does not own session restart behavior in any
harness. It therefore never launches, terminates, or mandates a session. The
default threshold of two confirmed compactions remains configurable and
experimental until comparative evaluation measures missed constraints,
repeated work, duplicate actions, verification failures, recovery time, tokens,
and latency against uninterrupted native compaction.
