---
type: llm
weight: 2
---
Pass only if ALL hold:
1. The output is the finished template only — no conversational preamble ("Here's…", "Sure"), no explanation of what was changed, no closing offer. (A wrapping code fence, and blueprint sections appended as part of the template — e.g. Risk Profiling, Schema Validation, Compute Matrix, Fallback Logic, telemetry JSON — are allowed; only conversational text addressed to the user counts as preamble/commentary.)
2. It has a concrete, action-oriented task definition with a checkable success condition (e.g. which dotfiles, where, what counts as a successful nightly backup).
3. Constraints require absolute paths — the backup destination is NOT left as `~/backups` or `$HOME/backups` unresolved (a placeholder like `/Users/<user>/backups` or an explicit "resolve to an absolute path" rule is fine).
4. Constraints require idempotency: re-running (e.g. nightly) must not duplicate backups or corrupt state.
5. It specifies a desired output/report format (e.g. table or JSON of files backed up/skipped).
