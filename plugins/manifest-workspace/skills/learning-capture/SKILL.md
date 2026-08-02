---
name: learning-capture
description: Append and query structured lessons in XDG data storage; capture is advisory and independent of the primary task verdict.
---

# Learning Capture

Run `scripts/learning_capture.py` with `add`, `query`, `list`, or `stats`.
Records are append-only JSON Lines at
`$XDG_DATA_HOME/manifest/knowledge/entries.jsonl`.

Required capture fields are category, language, and finding text. Valid
categories are `pattern`, `antipattern`, `tool-discovery`, and
`config-insight`. Never delete existing records. A malformed existing record
must surface an error instead of being overwritten.

Cross-domain consumers invoke `[[skill:learning-capture]]`; capture failure is
advisory and must not change their primary verdict.
