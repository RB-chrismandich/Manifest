---
type: regex
target: {source: file, path: .github/workflows/ci.yml}
match: not_contains
flags: i
weight: 0.5
---
go-version|node-version
