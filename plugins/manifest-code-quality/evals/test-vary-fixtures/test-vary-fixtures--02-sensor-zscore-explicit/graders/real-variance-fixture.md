---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the "normal"/spike-case test's `history` fixture contains at least two distinct values (nonzero variance) — e.g. alternating values like `[68.0, 70.0] * 3` — rather than a single repeated constant, AND the test asserts `sensor_z_score` returns a clearly anomalous (large, non-`None`, non-zero) z-score for a reading far from that history's mean. Score 0 if the "normal" case's history is all-identical values (which would make `stdev == 0` and force the degenerate `None` branch instead of a real z-score), or if no such spike assertion is present.
