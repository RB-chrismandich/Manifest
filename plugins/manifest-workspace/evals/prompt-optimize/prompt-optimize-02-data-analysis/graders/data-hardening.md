---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Output is the template only (no preamble or trailing commentary). (A wrapping code fence, and blueprint sections appended as part of the template — e.g. Risk Profiling, Schema Validation, Compute Matrix, Fallback Logic, telemetry JSON — are allowed; only conversational text addressed to the user counts as preamble/commentary.)
2. Defines churn precisely (e.g. subscription canceled / not renewed within the month) rather than leaving "churned" vague.
3. Includes input/schema validation: what to do with missing columns, nulls, or malformed rows in the CSV.
4. Includes a fallback path when the data fails validation (report and stop, not guess).
5. Specifies a strict output format (table or JSON schema) listing churned customers and a reason field that must be grounded in the data (not invented).
