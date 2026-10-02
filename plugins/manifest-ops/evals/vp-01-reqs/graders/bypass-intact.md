---
type: regex
target: {source: file, path: requirements.txt}
match: contains
flags: m
weight: 1
---
^internal-lib  # version-pin:ignore \(reason: vendored\)$
