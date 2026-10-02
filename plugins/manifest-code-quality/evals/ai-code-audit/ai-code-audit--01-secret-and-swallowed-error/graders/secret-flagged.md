---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the answer flags `DB_PASSWORD = "SuperSecret123!"` in app/config.py as a hardcoded/committed credential (a critical, security-tagged finding) and recommends loading it from the environment or a secrets manager instead of a source literal. Score 0 otherwise.
