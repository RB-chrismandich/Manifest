---
type: regex
target: {source: file, path: smoke-catalog/reports.yaml}
match: not_contains
weight: 0.5
---
command: "reports-cli export
