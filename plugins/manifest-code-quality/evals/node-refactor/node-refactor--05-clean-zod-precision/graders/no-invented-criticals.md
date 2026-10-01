---
type: llm
weight: 1
---
This module validates all input at the boundary with zod, infers a strict type from the schema (no `any`), and contains no injection, no secrets, no eval, no unvalidated I/O. Score 1 only if the answer does NOT invent a Critical or High severity finding (e.g. does not claim a security vulnerability, missing validation, or hardcoded secret in this snippet). Minor/Low advisories (e.g. "add unit tests for boundary ages", "export the schema for reuse") are fine. Score 0 if any Critical/High finding is fabricated.
