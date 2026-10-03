---
type: regex
target: last_message
match: contains
flags: i
---
gh pr (edit|view)\s+#?42\b[^\n]*(--base\s+main|baseRefName)
