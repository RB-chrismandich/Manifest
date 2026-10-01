---
type: llm
focus: last_message
weight: 1
---
Score 1 only if there is a SEPARATE, explicit test where `history` is constant/flat (e.g. `[70.0] * 6`) that asserts `sensor_z_score(reading, history) is None` (the function's defined degenerate result), clearly labeled as the zero-variance/degenerate edge case rather than folded into the spike test. Score 0 if this flat-baseline case is missing entirely, or if it's asserted to raise an exception / return `0.0` instead of `None`.
