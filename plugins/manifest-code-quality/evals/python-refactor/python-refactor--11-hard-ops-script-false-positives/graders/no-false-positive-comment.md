---
type: llm
weight: 1
---
The line `# password = "hunter2"  -- old creds, rotated 2019, kept here for incident history only` is a comment, not executable code, and is explicitly noted as rotated/retired. Score 1 only if the answer does NOT report this as a live hardcoded secret/credential finding (e.g. does not list it as a Critical/High "hardcoded password" issue requiring rotation). It is acceptable for the answer to suggest deleting the stale comment as a minor hygiene nit, or to ignore it entirely. Score 0 if it is reported as an active hardcoded secret vulnerability.
