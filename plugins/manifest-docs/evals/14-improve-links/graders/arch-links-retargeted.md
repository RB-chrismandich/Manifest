---
type: regex
target: {source: file, path: docs/ARCHITECTURE.md}
match: contains
weight: 0.5
---
^(?=[\s\S]*\]\(\.\./tally/ingest\.py\))(?=[\s\S]*\]\(\.\./tally/store\.py\))
