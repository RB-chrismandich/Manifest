---
type: llm
weight: 2
---
Pass only if ALL hold:
1. The template's constraints direct the implementation to follow the repo's bash/`.sh` convention (per docs/CODING_STANDARDS.md), rather than keeping "python script" from the raw prompt.
2. It does not require or suggest a Python implementation anywhere as the deliverable.
3. It includes idempotency (re-running the weekly rotation doesn't re-gzip or duplicate archives) and absolute log paths.
4. Output is the template only (no preamble or trailing commentary). (A wrapping code fence, and blueprint sections appended as part of the template — e.g. Risk Profiling, Schema Validation, Compute Matrix, Fallback Logic, telemetry JSON — are allowed; only conversational text addressed to the user counts as preamble/commentary.)
