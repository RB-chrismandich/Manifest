---
type: llm
weight: 1
---
Score 1 if the answer states there are no critical/high security findings — public access is blocked, encryption at rest is configured with KMS, versioning is enabled, and state uses an encrypted S3 backend with DynamoDB locking — while optionally noting minor advisories (e.g. add lifecycle rules, add a description/name tag). Score 0 if it concludes the module is unsafe to merge or invents a critical/high finding.
