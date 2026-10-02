---
type: llm
focus: trace
weight: 2
---
Judge the agent's answer to the user across ALL of its assistant messages in the trace (the final message may be a short coda). Pass only if ALL hold:
1. Extra spend is computed as 6,000 tokens/run (≈6M tokens/month at 1,000 runs).
2. Break-even miss rate is computed as 6,000 / 40,000 = 0.15 (15%).
3. It compares the observed 20% miss-rate reduction (v1 20% → v2 ≈0%) to the 15% break-even and concludes v2 nets positive (≈ 1000 × 0.20 × 40,000 − 6M = +2M tokens/month, or equivalent per-run +2,000).
4. Gives a clear verdict (switch to v2), not just a list of deltas.
Arithmetic errors in any of 1–3 are a fail.
