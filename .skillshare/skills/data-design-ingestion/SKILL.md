---
name: data-design-ingestion
description: Use when designing a local table that caches records fetched from an external feed — choose append-only+dedup vs full-replace based on whether the upstream data is immutable history or re-published-in-full.
---
# Choose Append-Only vs Full-Replace for Ingestion Tables

Both make re-runs idempotent, but the right choice depends on the upstream feed's
mutation model. Getting it wrong causes either row explosion, lost history, or
stale aggregates after upstream corrections.

## Decision

1. **Immutable historical facts** (government contract awards, completed trades):
   use **append-only** with a deterministic dedup id and `INSERT OR IGNORE`.
   - id = `sha1("{stable}:{fields}:{amount:.2f}")` — include every field needed to
     distinguish legitimately-separate records (e.g. the filer/agency), and format
     floats with fixed precision so the key is stable across runs.
   - Re-fetching the same window adds zero rows; cheap and history-preserving.
2. **Datasets re-published in full, subject to amendment** (disclosure feeds that
   correct prior filings): use **full-window replace** — `DELETE` the window then
   `INSERT`, inside a single transaction. Amendments are absorbed automatically; no
   per-record upsert/identity tracking needed.

## Guardrails

3. **Wrap multi-statement writes in one transaction** (`with conn:`), so a crash
   can't leave events updated but the derived aggregate stale.
4. **Guard the empty-feed case**: if the fetch returns zero rows, do NOT run the
   `DELETE` — preserve existing data and only bump the as-of/refresh timestamp.
5. **Separate raw from derived**: keep an append-only raw event log and a
   materialized summary table when a formula may change — you can recompute the
   summary from raw without re-hitting the API (`--recompute`). Drive staleness
   off the raw `fetched_at`, not the summary's `computed_at` (recompute refreshes
   the latter even on stale data).
