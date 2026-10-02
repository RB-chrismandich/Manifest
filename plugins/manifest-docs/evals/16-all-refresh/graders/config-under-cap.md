---
type: regex
target: {source: file, path: docs/CONFIGURATION.md}
match: not_contains
---
^(?:[^\n]*\n){400}[\s\S]
