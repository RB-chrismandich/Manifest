---
name: out-of-band-cache-warm
description: Use when an in-process HTTP client stalls at scale (thousands of sequential calls) but the endpoint itself is healthy — warm the cache out-of-band with a hard-deadline tool, then run the job cache-only.
---
# Warm the Cache Out-of-Band, Then Run Cache-Only

When a job makes many sequential paid/remote calls through one long-lived in-process client, the client (not the API) often degrades — pooled-connection hangs, gap-based timeouts that don't fire, server-side throttling under sustained load. Fighting the client in-loop is whack-a-mole. Decouple fetching from analysis.

1. **Confirm the endpoint is healthy out-of-band.** `curl --max-time 12` a few of the items that the in-process loop skipped/hung on. Fast 200s confirm the problem is the client, not the data.
2. **Warm the cache with a separate, hard-deadline fetcher.** Write a small `curl`-based script that loops the items, each with `--max-time N`, writing the same cache path/format the job reads. A hard total deadline per call cannot stall the way a gap-based read timeout can. Write `[]`/empty on any non-200 so a missing item never blocks.
3. **Use bulk/all-item endpoints where they exist** to collapse N calls to 1 (see the job's own client or the vendor's official client for `/bulk/...` or all-item variants). One 50MB fetch beats 347 per-item calls.
4. **Run the warming in the background and watch cache counts climb** (`ls <cachedir>/<dataset> | wc -l`) — steady growth, zero stalls, is the signal it's working.
5. **Then run the job cache-only.** With every remote response on disk, the job reads from cache and makes zero (or only unavoidable) live calls — it completes hang-free and deterministically.
6. **Keep the cache gitignored** when payloads are paid/proprietary, and treat any token shared in plaintext as exposed (rotate it).

