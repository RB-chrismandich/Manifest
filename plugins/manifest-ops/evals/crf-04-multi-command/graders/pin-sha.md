---
type: regex
target: last_message
match: contains
flags: i
weight: 0.5
---
headSha|head_sha|same commit|CI_COMMIT_SHA|(pipeline|commit|run)(.s)? sha
