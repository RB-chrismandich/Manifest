---
type: regex
target: {source: file, path: README.md}
match: contains
flags: i
---
threshold[^\n]*\b5\b
