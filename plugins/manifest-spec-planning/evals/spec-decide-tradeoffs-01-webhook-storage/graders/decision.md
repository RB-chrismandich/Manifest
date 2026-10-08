---
type: llm
focus: trace
weight: 1
---
PASS only if the trace and final answer show all of the following:
1. The assistant compares both supplied options on at least replayability/auditability, read cost, and operational complexity, using a concrete trade-off table rather than unsupported good/bad labels.
2. It makes one clear recommendation and names the trade that recommendation accepts; the mutable-row preference in the draft is considered but not treated as binding.
3. It records the chosen option and its rationale in `specs/webhook/design.md` under `Decisions`, preserving consistent names and adding no unsupported requirements.
4. The recommendation is not presented as universally best; it is tied to the supplied need to explain/replay failed attempts.
