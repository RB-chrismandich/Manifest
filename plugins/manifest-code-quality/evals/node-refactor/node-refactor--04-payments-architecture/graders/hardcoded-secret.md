---
type: llm
weight: 1
---
Score 1 only if the answer flags the literal `Authorization: "Bearer sk_live_51EXAMPLEKEY0000"` in `stripeCharge` as a hardcoded secret/API key committed to source, AND recommends loading it from an environment variable or secrets manager instead. Score 0 otherwise. (fake fixture value; gitleaks:allow)
