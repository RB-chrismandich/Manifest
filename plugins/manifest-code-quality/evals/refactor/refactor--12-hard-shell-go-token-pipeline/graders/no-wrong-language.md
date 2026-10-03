---
type: llm
focus: last_message
weight: 0.5
---
The code under review is shell (`run-release.sh`) and Go (`token-gen/main.go`).
Score 1 unless the answer gives findings or recommendations specific to an
unrelated ecosystem as part of the review — e.g. PEP 8 or Python docstrings, or
Terraform resources such as security groups or S3 buckets. Shell- and
Go-native advice is in scope. Stating that other tooling does not apply is
fine. Score 0 only if wrong-ecosystem advice is actually given.
