---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL hold:
1. It gives concrete Flask + Redis caching guidance (e.g. redis-py or Flask-Caching, a cache key for /products, a TTL).
2. It addresses invalidation or staleness (TTL expiry, delete-on-write, or similar).
3. It does NOT recommend a separate curl-based out-of-band warmer script with per-call --max-time deadlines.
