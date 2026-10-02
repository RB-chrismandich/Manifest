---
type: regex
target: {source: file, path: smoke-catalog/reports.yaml}
match: contains
weight: 1
---
- reports-cli
