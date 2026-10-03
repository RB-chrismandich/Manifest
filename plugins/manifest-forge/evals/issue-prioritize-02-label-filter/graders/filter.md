---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer ranks only `future`-labeled issues: #16 (no `future` label) stays outside the ranked list — excluded outright or explicitly called out as outside the filter. Fail if #16 appears in the ranking, even with an explanation.
