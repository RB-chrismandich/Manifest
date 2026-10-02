---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL hold:
1. It identifies the upstream endpoint/service as failing (the manual curl also times out / returns 503), not the local HTTP client.
2. It recommends upstream-appropriate actions: e.g. check vendor status/contact vendor, exponential backoff with jitter / respect Retry-After, pause and resume later, or checkpoint progress to resume.
3. It does NOT prescribe out-of-band cache warming followed by a cache-only run as the fix (warming cannot succeed while the endpoint returns 503).
