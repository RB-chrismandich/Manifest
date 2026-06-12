---
name: architecture-decision-tradeoff-table
description: >-
  Use when a design choice has multiple valid options and the user wants the
  best long-term solution (fidelity, accuracy, scale, maintainability) — produce
  a dimension-by-dimension trade-off table, justify one recommendation against
  long-term failure modes, and record it in the spec.
---
# Decide an Architecture Choice via a Trade-off Table

When a clarification or design question has several defensible answers and the user asks "which is the better long-term solution / most fidelity / most value," do not just pick — show the reasoning as a scored comparison, then commit the decision to the artifact. This recurs whenever a spec leaves a storage model, aggregation strategy, scoring formula, or fetch cadence open.

1. **Enumerate the real options (2–4).** State each as a concrete mechanism, not a label — e.g. "daily pre-aggregate, discard raw" vs "store raw alerts, aggregate at read time" vs "raw event log + materialized summary." Include any option the user already leans toward so it gets judged on equal footing.
2. **Pick the dimensions that actually matter for THIS choice.** Default long-term lenses: performance at scale (estimate the cost — "500 tickers × 252 days × 2 queries = 252k scans"), fidelity/information loss, audit trail / replayability, future signal extensibility, testability/isolation, idempotency, and schema/operational complexity. Drop dimensions that don't discriminate.
3. **Build the table.** One row per option (or per dimension), one column per dimension, with a terse concrete cell per intersection — not "good/bad" but *why* ("re-fetch required", "O(1) lookup", "gone after run").
4. **Name the disqualifiers explicitly.** For each rejected option, give the single sentence that kills it for long-term use: a one-way door (discards data you can't re-fetch), a constitution/principle violation (e.g. mutating an append-only audit table breaks replayability), or a known past failure (e.g. "same class of bug as the memoization emergency patch in 011").
5. **Recommend one, with the trade it accepts.** State the winner AND what you're paying for it ("one extra table") so the choice is honest, not sold.
6. **Make it tunable where the right value is uncertain.** If the decision hides a magic number (threshold, weight, window), promote it to a config field with a sensible default rather than hard-coding — note this in the recommendation.
7. **Record the decision in the artifact immediately.** Write it into the spec's Clarifications/Decisions section (or research.md) with the chosen option and the one-line rationale, so downstream planning and tasks inherit it. Keep field/entity names consistent with the rest of the artifact set — a rename here is a future cross-artifact finding.
