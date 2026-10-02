---
type: llm
---
Pass only if the answer rewrites the WHERE clause to a sargable range (`created_at >= '2025-01-01' AND created_at < '2026-01-01'`), suggests an index covering (status, created_at) or similar, and advises selecting only needed columns — and it does NOT produce a prompt/skill template (`<problem_structure>` etc.).
