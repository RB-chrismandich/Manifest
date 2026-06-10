---
name: statistical-test-fixture-variance
description: Use when writing or debugging unit tests for z-score, standard-deviation, normalization, or surge/ratio functions — constant or flat fixture data collapses the statistic to zero and silently fails the assertion. Build baselines with real variance.
---
# Give Statistical Test Fixtures Real Variance

A recurring, easy-to-miss test bug: a fixture builds a "baseline" series of identical values, the function under test computes `stdev`/`pstdev` over it, gets `0`, the z-score divides into `0.0`, and the spike assertion (`z > 2.0`) fails for a reason that looks like a logic bug but is a data bug. This bit anomaly-event detection and gamma-velocity scoring the same way.

1. **Spot the smell.** Any helper like `_flat_series(..., value=0.40)` or `[50.0 for _ in range(n)]` feeding a function that internally takes a standard deviation, z-score, normalization, or percent-change. Zero variance ⇒ degenerate statistic.
2. **Build baselines with non-zero variance on purpose.** Alternate or vary the values: `0.40 + (0.01 if i % 2 else -0.01)`, or `40.0/60.0` alternating. Keep the mean where you want it but ensure `stdev > 0` so the spike has something to be measured against.
3. **Keep the genuinely-flat case as its own explicit test.** Constant input is a real edge case — assert the function returns the *defined* degenerate result (z = 0.0 / None) rather than crashing or dividing by zero. Don't delete the flat fixture; relabel it as the std=0 test.
4. **Watch the fixture date/coordinate generators too.** Same class of silent bug: an f-string like `f"2026-0{i+1:02d}-01"` yields the invalid `2026-001-01` at i=9. Use explicit, validated date construction (`date(2026,1,1) + timedelta(days=i)` or a hand-written list) so the fixture itself can't be malformed.
5. **Confirm RED for the right reason.** When a TDD test fails, read the actual assertion/error before implementing — a `z == 0.0` failure means fix the fixture variance, not the production code. Only treat it as a real RED once the data is sound.
6. **Honor min-observation guards.** If the function requires `min_baseline`/`min_obs` prior points, give the fixture enough in-window rows; a too-short baseline is silently skipped, not an anomaly — and that's a separate intended behavior to test explicitly.
