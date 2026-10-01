---
type: regex
target: {source: file, path: data/manifest/knowledge/entries.jsonl}
match: contains
weight: 0.5
---
"KB-\d{3}"
