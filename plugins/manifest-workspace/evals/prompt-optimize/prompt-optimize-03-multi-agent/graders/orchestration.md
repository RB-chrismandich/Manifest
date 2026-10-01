---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Output is the template only (no preamble or trailing commentary). (A wrapping code fence, and blueprint sections appended as part of the template — e.g. Risk Profiling, Schema Validation, Compute Matrix, Fallback Logic, telemetry JSON — are allowed; only conversational text addressed to the user counts as preamble/commentary.)
2. Specifies exactly what state/inputs each reviewer receives and what each must return (a defined payload per sub-agent), not just "review the PR".
3. Specifies how results are aggregated (dedup/conflict handling, severity) into one report.
4. Requires a machine-readable final status/telemetry object (e.g. JSON with overall status, steps executed, per-reviewer results).
5. Includes an idempotency or re-run constraint (e.g. re-running doesn't post duplicate comments).
