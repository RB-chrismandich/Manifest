---
type: regex
target: {source: file, path: docker-compose.yaml}
match: contains
flags: im
weight: 0.5
---
internal:\s*true
