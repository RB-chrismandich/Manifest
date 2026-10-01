---
type: regex
target: {source: file, path: docker-compose.yaml}
match: not_contains
flags: im
weight: 1
---
hunter2
