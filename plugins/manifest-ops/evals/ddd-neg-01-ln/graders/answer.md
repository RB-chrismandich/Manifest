---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gives `ln -sfn <target> <link>` and explains -f and -n (so a symlink to a directory is replaced rather than descended into).
2. It does NOT frame the answer as deploy drift classification.
