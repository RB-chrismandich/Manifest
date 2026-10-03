---
type: regex
target: last_message
match: contains
flags: i
weight: 1
---
git reset --hard origin/main|git (switch|checkout) -[cbB][^\n]*origin/main|git rebase[^\n]*--onto origin/main
