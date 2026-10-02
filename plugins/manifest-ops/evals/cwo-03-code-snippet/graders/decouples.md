---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It states (or proposes verifying with an out-of-band request) that the remote endpoint is healthy and the long-lived in-process HTTP client is what degrades.
2. It recommends a SEPARATE fetcher (standalone script/process) that applies a hard total deadline per call (e.g. `curl --max-time N` or an equivalent total-timeout), writing responses into the same cache path/format the job reads.
3. It recommends running the main job cache-only (reading from the warmed cache, zero or minimal live calls) after warming.
4. It does NOT present raising in-process timeouts, adding retries, or adding threads/concurrency to the existing client as the primary fix.
5. The proposed warmer writes to `cache/<id>.json`, the same path and format that `load_all` reads.
