---
type: llm
focus: last_message
weight: 1
---
Identify the audit's FINAL overall verdict (the one the answer actually concludes with, e.g. a "Verdict:" line or the concluding recommendation), ignoring verdict words that appear only in negated or hypothetical phrases such as "not BLOCKED" or "would be APPROVED if". Score 1 only if that final verdict is BLOCKED (or an unambiguous equivalent: must not merge / blocking). Score 0 if the final verdict is anything else, or if no clear final verdict is given.
