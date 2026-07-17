---
name: api-optimize-bulk
description: Before running N sequential per-entity API calls, check vendor docs and client source for a bulk/aggregate endpoint that replaces them with one call
---
# API Bulk Endpoint Optimization

Trigger: you are about to loop an external API over many entities (per-ticker, per-user, per-repo), or an existing run
is slow/rate-limited because it does.

1. Estimate the cost of the naive path: N entities × M datasets = total calls and rough wall-clock. If N is large
   (hundreds+), pause before running.
2. Validate rate limits FIRST — do not assume. Fetch the official API docs AND read the official client's source for
   any sleep/retry/`min_interval`/backoff logic. Absence of throttling code means added client-side delays are pure
   overhead. **GitHub syntax shown below — GitLab uses a different endpoint**: if the client repo is on GitHub,
   `gh api repos/<org>/<client>/contents/<file>` (base64-encoded, needs decoding) fetches one file without cloning;
   on GitLab use `glab api projects/<id>/repository/files/<file>?ref=<branch>` instead, or just clone/`curl` the raw
   file for any other host.
3. Search the client's endpoint map and docs for bulk/aggregate variants: `/bulk/...`, `/live/...`, all-entity forms
   (calling the method with no entity argument), or a single endpoint returning all rows with full history.
4. Verify a candidate bulk endpoint live with one minimal authenticated request; confirm it (a) covers your entity
   universe, (b) returns the fields you need, and (c) has adequate history depth (a `/live/` snapshot is often shallower
   than per-entity history — note that tradeoff).
5. For each dataset, decide: true bulk (1 call, full history) → use it; snapshot-only bulk → use only if recency
   suffices; no bulk → keep per-entity but relax any invented rate limit.
6. Cache every response keyed by (dataset, entity-or-`_all`) so an interrupted or re-run job resumes near-instantly and
   only fetches gaps.
7. Filter the bulk result to your universe in-process (`{e for e in bulk() if e.id in members}`) rather than re-querying
   per entity.
8. Report the before/after: calls saved, coverage change, and runtime delta, so the optimization is auditable.
