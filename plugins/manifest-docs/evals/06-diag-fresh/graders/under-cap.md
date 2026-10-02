---
type: regex
target: {source: file, path: docs/ARCHITECTURE_DIAGRAMS.md}
match: not_contains
weight: 0.5
---
^(?:[^\n]*\n){300}[\s\S]
