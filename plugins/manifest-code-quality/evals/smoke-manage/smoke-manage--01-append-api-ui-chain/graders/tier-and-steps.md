---
type: regex
target: {source: file, path: smoke-catalog/billing.yaml}
match: contains
flags: i
weight: 1
---
tier: Lite[\s\S]*type: api[\s\S]*type: ui
