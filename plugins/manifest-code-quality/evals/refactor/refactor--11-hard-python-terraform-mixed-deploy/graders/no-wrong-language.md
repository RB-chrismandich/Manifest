---
type: llm
focus: last_message
weight: 0.5
---
The code under review is Python (`notify.py`) and Terraform (`iam.tf`). Score 1
unless the answer gives findings or recommendations specific to an unrelated
ecosystem as part of the review — e.g. Go goroutines, ShellCheck, npm/Node or
TypeScript tooling. Python-native advice is in scope, including async/await or
an async HTTP client to replace the blocking `curl` subprocess; Terraform/IAM
advice is in scope. Stating that other tooling does not apply is fine. Score 0
only if wrong-ecosystem advice is actually given.
