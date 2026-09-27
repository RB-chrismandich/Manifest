---
type: llm
focus: last_message
weight: 0.5
---
`sensor_z_score` as given is already correct (it has a proper `stdev == 0` guard). Score 1 if the answer does not claim the function itself is buggy or needs a code change — it should only be about test/fixture design. Score 0 if it asserts the implementation has a defect that isn't actually present (e.g. claiming it crashes on flat input, or that the formula is wrong).
