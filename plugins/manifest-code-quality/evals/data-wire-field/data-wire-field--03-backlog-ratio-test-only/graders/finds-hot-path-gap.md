---
type: llm
weight: 1
---
Score 1 only if the answer states that `run_pipeline` (via `fetch_and_build`)
never calls `_attach_backlog_ratio` — the only place that function is invoked is
the unit test — so every `RiskSnapshot` produced by `run_pipeline` in production
has `backlog_ratio=None` despite the test passing. It must explicitly note that
the passing unit test proves the math is correct but proves nothing about
production wiring, and recommend calling `_attach_backlog_ratio` inside
`run_pipeline`/`fetch_and_build` (or wherever snapshots are produced for real
use). Score 0 if it concludes the field is correctly wired because the unit test
passes, or does not identify that the hot path skips the attach call.
