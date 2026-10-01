---
type: regex
target: last_message
match: contains
flags: i
---
(basic ?auth|authentication|TLS).{0,80}(remov|lost|regress|dropp|no longer)|(remov|lost|regress|dropp|no longer).{0,80}(basic ?auth|authentication|TLS)
