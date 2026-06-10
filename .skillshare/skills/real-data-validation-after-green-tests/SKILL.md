---
name: real-data-validation-after-green-tests
description: Use after unit tests pass on data-processing code (parsers, aggregators, ETL, API ingest) and before merging — run the code against real or cached production data, because idealized test fixtures hide edge cases that live data exposes.
---
# Real-Data Validation After Green Tests

Green unit tests prove logic against the data you imagined. Real data carries shapes you didn't: free-text where you expected numbers, zero-variance series, ID collisions at scale, vendor string-casing drift. This skill is the validation pass that catches them. Trigger it whenever a feature ingests, parses, or aggregates external data and the suite is passing.

Recurring evidence: a suite went 290/290 green, then a live run surfaced three real bugs — `float()` crashing on `"Over $50,000,000"`, a composite ID colliding on ~20% of rows, and ~60% mismatch from `&` vs `and` casing. Separately, a flat test fixture (`pstdev=0`) masked a z-score that silently returned 0. Each was invisible to tests because fixtures used clean, idealized values.

## Steps

1. **Don't stop at green.** Treat a passing unit suite as necessary, not sufficient, for any code that touches external/real data. State explicitly that real-data validation is still pending.
2. **Find representative real input without new credentials.** Prefer a warm cache or fixture of real payloads already in the repo (e.g. `data/cache/**`) over live API keys. If a key-guarded CLI blocks the cache path, invoke the underlying module directly to exercise the cached data.
3. **Run the full pipeline end-to-end on real input**, not just the unit under test — fetch/parse → aggregate → persist → render. Bugs cluster at the seams between stages (a parser that tolerates a value the aggregator chokes on).
4. **Audit fixtures for idealization.** For each test, ask what real data does that the fixture doesn't: constant values (zero variance → division/stdev edge cases), always-numeric fields (free-text ranges, "Over $X", nulls), unique keys (real collisions), normalized casing/whitespace (vendor drift). Add a regression test reproducing each real shape you find.
5. **Quantify the gap.** Report match/collision/error rates over the real sample (e.g. "ID collided on N% of rows", "GICS matched 0%"), not just "it ran" — a silent wrong answer passes a smoke test.
6. **Fix root cause, then re-run on the same real sample** to confirm, and lock each finding with a fixture-based test so the next run can't regress.
7. **Only then claim done.** Note in the PR which real dataset validated the change and what it surfaced.

