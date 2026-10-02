---
type: llm
weight: 1
---
Score 1 only if the answer confirms the coverage gap is real and pinpoints the
exact cause: `build_alert_context`'s `dataclasses.replace` call only sets
`volatility_flag` and never includes `momentum_score`, even though
`compute_momentum_score` exists and computes a real value — so `momentum_score`
stays `None` all the way to `build_alert_prompt`. It must recommend the concrete
fix of adding `momentum_score=compute_momentum_score(ticker)` into that
`dataclasses.replace` call (or an equivalent additional replace step) inside
`build_alert_context`. Score 0 if it says the gap is a false positive / not a real
bug, or fails to name the missing argument in the existing `replace` call as the
fix site.
