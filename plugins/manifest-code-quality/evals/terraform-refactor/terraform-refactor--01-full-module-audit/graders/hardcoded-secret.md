---
type: llm
weight: 1
---
Score 1 only if the answer flags `variable "db_password"` having a hardcoded literal `default` password as a secret checked into source, AND recommends removing the default, marking the variable `sensitive = true`, and/or sourcing the value from a secret manager (e.g. AWS Secrets Manager or SSM Parameter Store) instead. Score 0 otherwise.
