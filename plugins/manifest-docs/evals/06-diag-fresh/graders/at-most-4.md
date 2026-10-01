---
type: regex
target: {source: file, path: docs/ARCHITECTURE_DIAGRAMS.md}
match: not_contains
---
(?:```mermaid[\s\S]*?){5}
