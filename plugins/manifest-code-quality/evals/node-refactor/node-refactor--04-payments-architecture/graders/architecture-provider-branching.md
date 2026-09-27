---
type: llm
weight: 1
---
Score 1 only if the answer identifies the string-branching on `currentProvider` in `charge()` (plus the module-level provider state) as the architectural cause of the reported pain point (every new provider means editing this function), AND proposes replacing it with per-provider implementations behind a common interface — e.g. a `PaymentProvider` interface/strategy with one implementation per provider, selected via dependency injection OR a registry/map keyed by provider name. Showing this in rewritten code counts. Score 0 otherwise.
