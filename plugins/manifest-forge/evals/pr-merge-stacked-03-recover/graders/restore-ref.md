---
type: regex
target: last_message
match: contains
flags: i
---
git push\s+(-\S+\s+)*origin\s+\S+:(refs/heads/)?feat-parser
