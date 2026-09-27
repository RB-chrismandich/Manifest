---
type: regex
target: last_message
match: contains
flags: i
---
matrix:[\s\S]*3\.11[\s\S]*3\.12|matrix:[\s\S]*3\.12[\s\S]*3\.11
