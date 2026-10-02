---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It treats phase 4 as a new, independent bottleneck and repeats the measure-and-classify loop there (profile/time phase 4 on real data).
2. It advises against bundling speculative fixes (retries, bigger thread pool, orjson) that aren't tied to a measured cause.
3. It recommends re-measuring with the same progress proxy after each fix, and keeping incremental caching so re-runs resume fast.
