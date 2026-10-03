---
type: llm
weight: 1
---
Score 1 only if the fix moves, duplicates, or restructures the rejection warning so it fires before or regardless of the empty-`valid` early exit — e.g. emitting the `rejected > 0` warning ahead of the `${#valid[@]} -eq 0` check, or folding the rejection count into whatever message is printed at exit for the empty case. Score 0 if the fix leaves the warning strictly after the early exit, so the all-rejected case stays silent.
