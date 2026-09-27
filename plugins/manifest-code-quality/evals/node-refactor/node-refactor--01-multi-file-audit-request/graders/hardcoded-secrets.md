---
type: llm
weight: 1
---
Score 1 only if the answer flags both `jwtSecret` and `stripeKey` in `src/config.ts` as hardcoded secrets committed to source, rates it Critical, AND recommends loading them from environment variables (e.g. `process.env.JWT_SECRET`) or a secrets manager instead. Score 0 otherwise.
