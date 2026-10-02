---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `compute_liquidity_score` is defined in
`enrich.py` but nothing ever calls it and attaches its result back onto the
snapshot (e.g. via `dataclasses.replace(snap, liquidity_score=...)`) — only
`attach_momentum` performs a replace, and it only sets `momentum_score`. Because
`PortfolioSnapshot` is frozen, `snap.liquidity_score` therefore stays at its
`None` default all the way to `build_prompt`. The answer must propose a concrete
fix: calling `compute_liquidity_score` and merging its result via
`dataclasses.replace(snap, liquidity_score=...)` at the missing join point (e.g.
alongside or after `attach_momentum`). Score 0 if it says `liquidity_score` is
already correctly wired, or only flags unrelated issues without naming this
missing population call.
