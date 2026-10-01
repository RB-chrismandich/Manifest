---
type: llm
weight: 1
---
Score 1 only if the answer identifies the `aws_iam_policy.deploy` statement's `Action = "*"` and `Resource = "*"` as an overly permissive, least-privilege violation granting unrestricted access to every AWS action and resource, AND recommends scoping `Action`/`Resource` down to the specific services and ARNs the deploy role actually needs. (Also noting the missing `backend` block means state is stored locally without remote locking is a bonus, not required.) Score 0 if the IAM wildcard issue is missing or misdiagnosed.
