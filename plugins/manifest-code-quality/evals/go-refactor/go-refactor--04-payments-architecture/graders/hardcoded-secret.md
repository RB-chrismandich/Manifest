---
type: llm
weight: 1
---
Score 1 only if the answer flags `const stripeSecretKey = "sk_live_..."` as a hardcoded credential/secret, rates it Critical, AND recommends sourcing it from an environment variable or secrets manager instead. Score 0 otherwise.
