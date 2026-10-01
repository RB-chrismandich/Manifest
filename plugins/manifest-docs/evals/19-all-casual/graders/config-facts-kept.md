---
type: regex
target: {source: file, path: docs/CONFIGURATION.md}
match: contains
flags: i
---
^(?=[\s\S]*threshold[^\n]*\b5\b)(?=[\s\S]*tally\.db)(?=[\s\S]*window_minutes[^\n]*\b60\b)
