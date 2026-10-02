---
type: llm
weight: 1
---
Score 1 only if the answer flags BOTH: (1) `DB_PASS=hunter2` as a hardcoded plaintext credential, and (2) `echo "connecting with password $DB_PASS"` as leaking that password to stdout/logs, AND recommends removing the hardcoded value (sourcing it from env/secret store) and not echoing secrets. Score 0 if either half is missing.
