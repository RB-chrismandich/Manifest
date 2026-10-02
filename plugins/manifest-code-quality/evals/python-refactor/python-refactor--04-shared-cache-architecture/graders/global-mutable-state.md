---
type: llm
weight: 1
---
Score 1 only if the answer flags the module-level `CACHE = {}` dict as shared mutable global state that functions read and write directly (an architecture/concurrency-safety issue causing the team's "stepping on each other's changes" symptom), AND proposes a fix such as passing the cache/store explicitly (dependency injection), encapsulating it behind a class instance, or using a proper cache/store abstraction instead of a bare module-level dict. Score 0 otherwise.
