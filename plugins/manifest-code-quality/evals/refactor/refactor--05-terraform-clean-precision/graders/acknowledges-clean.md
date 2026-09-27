---
type: llm
weight: 1
---
Score 1 if the answer, in Terraform/IaC-appropriate terms, states there are no critical/high security findings — public access is blocked on the bucket and server-side encryption is configured with KMS — while optionally noting minor advisories (e.g. add versioning, add tags). Score 0 if it invents a critical/high finding (e.g. claims the bucket is publicly exposed or unencrypted) or answers with generic non-IaC advice.
