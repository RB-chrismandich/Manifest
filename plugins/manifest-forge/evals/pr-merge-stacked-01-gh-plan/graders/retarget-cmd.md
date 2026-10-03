---
type: regex
target: last_message
match: contains
flags: i
---
(gh pr edit\s+#?42\b[^\n]*--base[ =]main\b|gh pr view\s+#?42\b[^\n]*baseRefName)
