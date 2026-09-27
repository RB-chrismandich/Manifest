---
type: llm
weight: 1
---
Score 1 only if the answer flags the hardcoded `STRIPE_API_KEY = "sk_live_..."` string literal in `billing/config.py` as a hardcoded secret / exposed credential, rates it Critical severity, AND recommends loading it from an environment variable or secrets manager instead. Score 0 otherwise.
