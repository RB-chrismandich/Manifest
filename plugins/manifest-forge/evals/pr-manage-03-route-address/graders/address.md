---
type: llm
focus: last_message
weight: 1
---
Pass if the answer agrees the comment is valid per the spec, proposes fixing the regex (e.g. `^-?\d+$`) with a test for a negative value, and replying in the thread with the fix commit/evidence before resolving.
