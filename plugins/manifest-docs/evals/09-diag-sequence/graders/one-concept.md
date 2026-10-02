---
type: regex
target: {source: file, path: docs/ingest-flow.md}
match: not_contains
weight: 0.5
---
(?:```mermaid[\s\S]*?){3}
