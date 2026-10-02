---
type: regex
target: {source: file, path: requirements.txt}
match: not_contains
flags: m
weight: 1
---
^(requests|flask)==\S+\s*$
