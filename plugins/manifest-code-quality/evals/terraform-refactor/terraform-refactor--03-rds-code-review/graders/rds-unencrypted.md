---
type: llm
weight: 1
---
Score 1 only if the answer flags `storage_encrypted = false` as leaving the production database's data at rest unencrypted — a critical/high risk — AND recommends setting `storage_encrypted = true`. (Noting that AWS RDS cannot enable encryption in-place on an existing instance and would require recreating/migrating via snapshot is a bonus, not required.) Score 0 if this finding is missing.
