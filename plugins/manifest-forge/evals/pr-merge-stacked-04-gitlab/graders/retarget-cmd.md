---
type: regex
target: last_message
match: contains
flags: i
---
(glab mr update\s+!?13\b[^\n]*--target-branch[ =]main\b|glab mr view\s+!?13\b[^\n]*target_branch|target branch[^\n]{0,60}main)
