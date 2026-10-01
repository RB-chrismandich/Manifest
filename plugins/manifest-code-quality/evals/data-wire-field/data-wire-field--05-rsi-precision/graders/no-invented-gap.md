---
type: llm
weight: 1
---
Score 1 only if the answer confirms `rsi` is correctly wired end-to-end: computed
by `compute_rsi` inside `run`, passed into `build_entry`, attached onto the frozen
`WatchlistEntry` via `replace(entry, rsi=rsi_value)`, and read correctly in
`render`. It must NOT claim `rsi` is unpopulated, never wired, or stuck at its
default. Score 0 if it invents a missing-population bug for `rsi` that isn't
actually present in this code.
