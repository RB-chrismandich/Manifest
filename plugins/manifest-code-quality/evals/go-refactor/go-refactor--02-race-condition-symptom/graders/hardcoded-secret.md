---
type: llm
weight: 1
---
Score 1 only if the answer flags `const adminToken = "sk-admin-..."` as a hardcoded credential, ALSO notes that it is being logged in plaintext via `fmt.Println(..., "token", adminToken)` (secret leaking into logs), rates it Critical, AND recommends removing the hardcoded token (load from env/secret store) and not logging secret values. Score 0 if either the hardcoding or the logging-of-secrets aspect is missing.
