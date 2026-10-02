---
type: regex
target: {source: file, path: README.md}
match: not_contains
---
^(?:[^\n]*\n){200}[\s\S]
