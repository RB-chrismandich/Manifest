---
type: llm
focus: {source: file, path: data/manifest/knowledge/entries.jsonl}
weight: 2
---
Pass only if ALL hold:
1. Every line is valid JSON.
2. The store contains a record with id `ANTI-001` (the seed "Unquoted variable expansion in shell commands") whose occurrence count is greater than its prior value (e.g. `occurrences` ≥ 2), plus last-seen metadata.
3. It does NOT contain a new `KB-NNN` record duplicating the unquoted-variable lesson.
