---
type: llm
focus: trace
weight: 2
---
Judge the agent's answer to the user across ALL of its assistant messages in the trace (the final message may be a short coda). Pass only if ALL hold:
1. Does NOT give a definitive yes/no verdict — it says the answer depends on data not yet available.
2. Names the missing inputs: the rework/cleanup cost per incident (R); how often each version's output needs rework (v1's and v2's miss rates, or the reduction between them); and v1's absolute per-run token cost (or the absolute extra tokens per run), since a 30% relative premium alone cannot be turned into extra spend per run.
3. Says R must be MEASURED (e.g. hand an agent v1's flawed output plus the original task and measure the tokens to discover and fix what was missed, over a few runs) rather than assumed/estimated.
4. Gives the break-even relation (required miss-rate reduction Δp* = extra spend per run / R, or net = runs × (p_v1 − p_v2) × R − total extra spend, where total extra spend = runs × extra spend per run; subtracting a per-run figure only once is wrong). The single-rate form (runs × p × R) passes only if it states v2's miss rate is assumed ≈ 0.
