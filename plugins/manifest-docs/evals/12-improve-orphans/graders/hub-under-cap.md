---
type: regex
target: {source: file, path: docs/README.md}
match: not_contains
weight: 0.5
---
^(?:[^\n]*\n){120}[\s\S]
