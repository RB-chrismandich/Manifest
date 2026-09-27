---
type: llm
weight: 2
---
Pass only if the final reply asks exactly ONE targeted clarifying question about a genuinely ambiguous, decision-changing detail (e.g. cache lifetime/TTL, in-process vs shared cache, or invalidation) before writing caching code — OR, if it implemented caching, it chose a clearly stated default and the reply is ≤ 3 lines. A reply that asks several questions, or writes long speculative code plus explanation, fails.
