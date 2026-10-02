---
type: regex
target: {source: file, path: docker-compose.yaml}
match: not_contains
flags: m
weight: 1
---
image:\s*\S+:\d[\w.-]*\s*$
