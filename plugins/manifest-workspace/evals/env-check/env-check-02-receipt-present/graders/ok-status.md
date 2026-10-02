---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Reports the receipt as present/readable and the status as ok (not degraded).
2. Lists availability for each of the six harnesses (claude, codex, gemini, cursor, antigravity, devin), marking each available or missing — values may vary by machine; what matters is that each is reported, and the answer is consistent with what the tool output/trace shows.
3. Treats unavailable optional harnesses as informational, not as a failure of the check.
