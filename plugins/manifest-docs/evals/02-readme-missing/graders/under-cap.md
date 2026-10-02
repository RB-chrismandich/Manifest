---
type: regex
target: {source: file, path: README.md}
match: not_contains
weight: 0.5
---
^(?:[^\n]*\n){200}[\s\S]
