---
name: live-data-smoke-validation
description: Use after unit tests pass but before merging a data-pipeline/integration feature — run the new code against real or cached data to surface bugs unit tests cannot catch.
---
# Live-Data Smoke Validation

Unit tests with synthetic fixtures pass while real payloads break the code. This step runs the feature end-to-end against real/cached data to catch integration bugs (malformed values, ID collisions, format mismatches) before they reach review.

1. **Locate real inputs without burning API quota.** Check for a warm cache (`data/cache/...`), `.env` keys, or a committed sample payload first. Cached data lets you exercise the real code path even when no API key is set.
2. **Drive the actual CLI/entry point**, not a reimplementation — invoke the same command an operator would run. If an API-key guard blocks the cache path, run the underlying module directly to reach the cached data.
3. **Watch specifically for the bug classes fixtures miss:**
   - free-text where a number is expected (`"Over $50,000,000"` → `float()` crash; use a range/midpoint parser)
   - dedup-key collisions across rows that share the obvious key (add a disambiguating field; `INSERT OR IGNORE`)
   - format normalization gaps between sources (`"A & B"` vs `"a and b"`; normalize both sides of the join)
   - staleness/time logic keyed on the wrong clock (wall-clock vs record date)
4. **For each bug found, add a regression test** that encodes the real-world shape, then fix, then confirm the full suite stays green.
5. **Re-run lint on touched files and commit the fixes** as a distinct "validation surfaced N bugs" commit so reviewers see what live testing caught.
6. Treat any task labelled "real-data validation" as mandatory before merge — it is the cheapest place to catch what review and CI won't.
