---
type: llm
focus: last_message
weight: 1
---
The same rule (E722 bare except) fired identically in three files (users.py, orders.py, payments.py) — this is one recurring pattern, not three unrelated defects. Score 1 only if the answer proposes/records ONE consolidated antipattern entry covering the pattern across all three locations (mentioning the three files as instances of the same issue), rather than three separate, independently-titled findings. Score 0 if it treats them as unrelated or only reports on one file while ignoring the other two.
