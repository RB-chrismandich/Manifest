---
type: llm
weight: 1
---
This module is already hardened: public access is blocked on all four flags, server-side encryption uses a KMS key, versioning is enabled, and the backend is a remote encrypted S3 backend with a DynamoDB lock table. Score 1 only if the answer does NOT report a Critical/High finding for bucket ACL/public exposure, encryption at rest, versioning, or state backend/locking. Score 0 if it invents such a finding on any of those already-handled areas.
