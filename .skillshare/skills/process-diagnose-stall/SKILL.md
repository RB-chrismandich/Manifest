---
name: process-diagnose-stall
description: Use when a long-running background job (data pipeline, batch fetch, analysis run) stops making progress — measure its resource signature to classify the stall instead of guessing fixes.
---
# Diagnose a Stalled Background Process

A long run that "hangs" has a few distinct causes with distinct fixes. Guessing wastes whole run cycles (each restart costs minutes). Measure first, classify, then fix the actual cause.

1. **Confirm it's actually stalled, not just quiet.** Compare a progress proxy across two checks ~60-120s apart: newest cache-file mtime (`ls -lt <cachedir> | head`), output-file bytes, or a per-item counter. Flat across two checks = stalled. Growing = healthy but slow (leave it).
2. **Read the resource signature** of the worker PID: `ps -o pid,stat,%cpu,etime,command -p <pid>`.
   - **`R` + ~100% CPU** → CPU-bound blowup, not a hang. Look for an O(n²)/unbounded computation on a larger-than-expected dataset (e.g. unfiltered full-history events fed into a per-date benchmark, or an expensive call invoked in an inner loop). Fix = bound the input (window-filter) and/or memoize the hot call.
   - **`S`/`0% CPU` + no cache writes** → blocked on I/O. Check `lsof -nP -p <pid> | grep ESTABLISHED` for a hung socket.
3. **For CPU-bound: profile or time the steps.** `py-spy dump --pid <pid>` for a live stack, or kill and run a small harness that times each phase on the real data (`t=time.time(); step(); print(time.time()-t)`). The 64s-vs-3s step is the culprit; the rest is noise.
4. **For I/O hangs: compare in-process vs out-of-band.** Probe the same endpoint with `curl --max-time N`. If curl returns fast but the in-process client hangs, it's the *client* (stale keep-alive socket, gap-based read timeout that never fires on a trickle response), not the server or any specific item. Fix = fresh connection per request (`max_keepalive_connections=0`) or a hard total deadline.
5. **Fix the measured cause, not a plausible one.** Re-run and re-measure with the same progress proxy. If a *different* phase now stalls, repeat — multiple independent bottlenecks are common; resist bundling speculative fixes.
6. **Preserve partial work between attempts.** Ensure the job caches incrementally so each kill/fix/re-run resumes near-instantly instead of refetching.

