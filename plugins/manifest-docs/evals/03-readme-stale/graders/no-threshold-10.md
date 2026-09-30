---
type: regex
target: {source: file, path: README.md}
match: not_contains
flags: i
---
default[^\n]*threshold[^\n]*\b10\b|threshold[^\n]*default[^\n]*\b10\b|default[^\n]*\b10\b[^\n]*threshold|\|\s*`?threshold`?\s*\|\s*`?10`?\s*\|
