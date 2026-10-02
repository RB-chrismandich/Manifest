---
type: regex
target: {source: file, path: Dockerfile}
match: contains
flags: m
weight: 1
---
^FROM python:3\.12$
