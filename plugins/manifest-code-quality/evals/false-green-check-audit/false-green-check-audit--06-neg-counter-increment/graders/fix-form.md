---
type: regex
target: last_message
match: contains
weight: 0.5
---
count=\$\(\(\s*count\s*\+\s*1\s*\)\)|\(\(\s*count\+\+\s*\)\)\s*\|\|\s*true|:\s*\$\(\(\s*count\+\+\s*\)\)|\(\(\s*\+\+count\s*\)\)|\(\(\s*count\s*\+=\s*1\s*\)\)|let\s+"?count\+=1"?\s*\|\|\s*true
