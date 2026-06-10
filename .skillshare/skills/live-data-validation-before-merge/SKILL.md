---
name: live-data-validation-before-merge
description: Use before merging a feature that ingests or transforms external/real data (APIs, bulk feeds, caches) — run it against real or cached data to surface bugs that unit tests with clean fixtures miss.
---
# Validate Against Real Data Before Merge

Unit tests use tidy fixtures; real feeds are messy. Running the feature against
actual cached/live data repeatedly surfaced bugs that green tests hid: `float()`
crashing on free-text range strings ("Over $50,000,000"), ~20% ID collisions from
a dedup key missing a distinguishing field, and a ~0% lookup match rate from a
casing/punctuation mismatch ("A & B" vs "a and b").

## Steps

1. **Find a real data source** without burning API budget: look for a warm cache
   directory (`data/cache/...`) or a populated dev DB before reaching for live keys.
2. **Run the real path**, bypassing only the API-key guard if the cache serves the
   data without a key. Drive a representative sample (not one clean ticker — pick
   one with many/odd records).
3. **Watch for the messy-data failure classes:**
   - Parsers assuming numeric where the feed sometimes returns free text/ranges.
   - Dedup/primary keys that collide when a distinguishing field is omitted.
   - Join/lookup keys that mismatch on case, punctuation (`&` vs `and`), or whitespace.
   - Empty-feed handling that deletes good data (guard zero-row responses).
4. **For each bug found, add a regression test** using the exact malformed input,
   then fix. Re-run the real-data pass until clean.
5. **Record what was validated** (sample size, source, date) in the PR/commit so
   the "live validation" task is auditable, not just checked off.
