---
name: live-data-validation
description: Use after unit tests pass on a data-ingestion or API-integration feature, before merging — run the code against real API/production data to surface bugs that synthetic fixtures hide.
---
# Live-Data Validation

Green unit tests built on hand-written fixtures routinely miss bugs that only real upstream data exposes. Run a live/real-data pass as an explicit gate before merge. This recurs on every data-feed feature and catches a predictable bug class.

1. **Treat it as a distinct task, not an afterthought.** Add an explicit validation task (e.g. "T032: live-API validation") so it isn't skipped when unit tests go green.
2. **Prefer a warm local cache if live keys are absent.** If the API key isn't set, look for cached payloads (`data/cache/...`) and drive the module directly, bypassing the key guard — you still exercise the real data shape.
3. **Hunt the fixture-blind bug classes specifically:**
   - **Free-text numeric fields** — values like `"Over $50,000,000"` crash `float()`; use a range/midpoint parser. Fixtures use clean numbers and never hit this.
   - **Dedup-key collisions** — real feeds have multiple rows sharing your composite key (same ticker/date/amount, different filer). Add a disambiguating field + `INSERT OR IGNORE`.
   - **Formatting mismatches in lookups** — upstream casing/punctuation (`"SEMICONDUCTORS & RELATED"` vs seed `"... and ..."`) silently yields ~0% join rate. Normalize both sides in the query.
   - **Falsy-zero and null confusion** — `if value:` drops legitimate `0.0`; use `if value is not None`.
4. **Run end-to-end on a representative real entity** and assert the output is sane (non-null, in expected range), not just that it didn't crash. Pick an entity you know should produce a signal.
5. **For each bug found, add a regression test using the real-data shape**, then re-run the full suite to confirm green before merging.
6. **Report what was validated and what was deferred** (e.g. "validated on 347 cached tickers; perf benchmark deferred") so coverage gaps are explicit.
