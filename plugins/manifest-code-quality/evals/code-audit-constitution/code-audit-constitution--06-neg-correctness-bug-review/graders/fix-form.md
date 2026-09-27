---
type: regex
target: last_message
match: contains
---
len\(s\)\s*-\s*i\s*-\s*1|len\(s\)\s*-\s*1\s*-\s*i|s\[::-1\]|s\[-i\s*-\s*1\]|s\[-\(i\s*\+\s*1\)\]|s\[~i\]
