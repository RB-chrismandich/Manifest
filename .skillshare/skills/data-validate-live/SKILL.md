---
name: data-validate-live
description: Validate data-ingestion, parsing, ETL, or API-integration code against real/live data — smoke pass, pre-merge gate, or post-unit-test. Surfaces fixture-blind bugs (free-text numerics, dedup-key collisions, casing/format mismatches, falsy-zero) that synthetic fixtures hide.
---
# Live-Data Validation

Green unit tests prove logic against the data you imagined; real feeds carry shapes you didn't. Run a live/real-data
pass against any feature that ingests, parses, or aggregates external data — treat it as mandatory before merge, not an
afterthought. This recurs on every data-feed feature and catches a predictable bug class that review and CI won't.

## Shared core

1. **Treat it as a distinct, mandatory task.** Add an explicit validation task (e.g. "T032: live-API validation") so it
   isn't skipped when unit tests go green.
2. **Find real input without burning API budget or new credentials.** Prefer a warm cache (`data/cache/...`), a
   populated dev DB, `.env` keys, or a committed sample of real payloads before reaching for live keys. If an API-key
   guard blocks the cache path, drive the underlying module directly — you still exercise the real data shape.
3. **Drive the actual CLI/entry point, not a reimplementation** — invoke the same command an operator would run.
4. **Pick a messy, representative sample** — one with many/odd records that you know should produce a signal, not one
   clean ticker. (Stricter rule: a single clean entity is not a valid sample.)
5. **Hunt the fixture-blind bug classes specifically:**
   - **Free-text numeric fields** — values like `"Over $50,000,000"` crash `float()`; use a range/midpoint parser.
     Fixtures use clean numbers and never hit this.
   - **Dedup-key collisions** — real feeds have multiple rows sharing your composite key (same ticker/date/amount,
     different filer). Add a disambiguating field + `INSERT OR IGNORE`.
   - **Formatting mismatches in lookups/joins** — upstream casing, punctuation (`"A & B"` vs `"a and b"`), or whitespace
     drift silently yields ~0% join rate. Normalize both sides.
   - **Falsy-zero and null confusion** — `if value:` drops legitimate `0.0`; use `if value is not None`.
   - **Empty-feed handling** — guard zero-row responses so they don't delete good data.
   - **Zero-variance series** — constant values (`pstdev=0`) mask division/stdev edge cases (e.g. a z-score silently
     returning 0).
   - **Staleness/time logic keyed on the wrong clock** — wall-clock vs record date.
6. **Quantify the result, don't just check for crashes.** Report match/collision/error rates over the real sample (e.g.
   "ID collided on N% of rows", "GICS matched 0%") and assert outputs are sane (non-null, in expected range). (Stricter
   rule wins: "it ran" is not validation — a silent wrong answer passes a smoke test.)
7. **For each bug found, add a regression test encoding the exact real-data shape**, fix root cause, then re-run on the
   same real sample plus the full suite until both are clean.
8. **Report what was validated and what was deferred** (e.g. "validated on 347 cached tickers; perf benchmark deferred")
   so coverage gaps are explicit.

## Smoke

Quick pass to catch integration bugs before they reach review:

- Run the feature end-to-end on cached/real data as soon as the code path works — cheapest place to catch what review
  and CI won't.
- Re-run lint on touched files and commit the fixes as a distinct "validation surfaced N bugs" commit so reviewers see
  what live testing caught.

## Before merge

Comprehensive gate on the PR:

- Re-run the real-data pass until clean — no known messy-data failures may ride into the merge.
- Record what was validated (sample size, source, date) in the PR/commit so the "live validation" task is auditable, not
  just checked off.

## After green tests

Confirmation step triggered by a passing suite on data-processing code:

- **Don't stop at green.** A passing unit suite is necessary, not sufficient; state explicitly that real-data validation
  is still pending.
- **Run the full pipeline end-to-end** — fetch/parse → aggregate → persist → render — not just the unit under test. Bugs
  cluster at the seams between stages (a parser that tolerates a value the aggregator chokes on).
- **Audit fixtures for idealization.** For each test, ask what real data does that the fixture doesn't: constant values,
  always-numeric fields, unique keys, normalized casing/whitespace. Add a regression test reproducing each real shape
  you find.
- **Only then claim done.** Note in the PR which real dataset validated the change and what it surfaced.

> Absorbed: live-data-validation-before-merge, live-data-smoke-validation, real-data-validation-after-green-tests
> (2026-06)
