---
type: regex
target: {source: file, path: README.md}
match: not_contains
---
^(?:[^\n]*\n){54}[\s\S]
