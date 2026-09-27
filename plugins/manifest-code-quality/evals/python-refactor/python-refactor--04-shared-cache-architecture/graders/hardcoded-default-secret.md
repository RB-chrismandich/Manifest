---
type: llm
weight: 1
---
Score 1 only if the answer flags the default parameter value `db_password="admin123"` as a hardcoded credential/secret (at any severity), AND recommends removing the hardcoded default and sourcing the password from an environment variable, secret manager, or a required (non-defaulted) argument. Score 0 otherwise.
