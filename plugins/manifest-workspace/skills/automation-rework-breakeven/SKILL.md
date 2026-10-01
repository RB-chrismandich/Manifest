---
name: automation-rework-breakeven
description: Use when deciding whether a more-thorough-but-costlier automation or skill version is worth it, e.g. weighing a v2 skill's extra token spend against the rework it avoids — measure the rework cost empirically rather than assuming it.
---
# Break-Even Analysis for a More-Correct, Costlier Automation

When a v2 of a skill/automation is more correct but spends more tokens per run, "is it worth it?" is a measurable
question, not a vibe. Distinct from `/manifest-workspace:token-benchmark` (config-deployment overhead) and
`skill-creator` benchmarking (raw pass/time/tokens): this models the *correctness-for-tokens trade* with an
empirically measured rework cost.

1. **Separate the two axes.** Correctness (pass rate) and cost (tokens/time) are independent — a version that "finds
   more" is not automatically cheaper. State both; never let a pass-rate win imply a token saving.
2. **Compute extra spend.** Take per-run token means for each version (averaged across evals) and the delta. Project
   it over N runs — that is the known cost the costlier version must earn back.
3. **Write the net model:** `net = runs × (p_v1 − p_v2) × R − extra_spend`, where `p_vN` = fraction of runs of
   that version that trigger a cleanup/follow-up, and `R` = tokens for one rework incident. Measure `p_v2` too —
   never assume the costlier version eliminates every miss; if it is unknown, the verdict is unknown.
4. **Measure R — do not assume it.** Run a recovery session: hand an agent the cheaper version's (incomplete/wrong)
   output and the original task, and have it discover and fix what was missed. Average 2-3 runs for `R ± spread`.
5. **Apply the salvage-value insight.** A confidently-wrong output has near-zero salvage value, so rework often costs
   ≈ a fresh full run. A large `R` lowers the break-even `Δp*`, so a small premium can buy out full-price redos — but
   only if the costlier version actually avoids misses: it nets positive only when observed `p_v1 − p_v2` exceeds
   `Δp*`. Equal nonzero miss rates mean the premium never earns back.
6. **Report a verdict, not just deltas.** Compute the break-even reduction `Δp* = extra_spend / (runs × R)` (the
   `net = 0` point; `extra_spend` is the step-2 total over `runs`, so equivalently per-run premium ÷ `R`), then compare
   it to the *observed* reduction `p_v1 − p_v2` (e.g. from evals) to say plainly whether it nets positive and under what
   usage mix.
7. **Persist the baseline to memory** (per-run costs, measured R, break-even rate, usage assumption) so future
   sessions don't re-derive it.
