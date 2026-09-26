---
type: llm
focus: last_message
weight: 1
---
Score PASS only if the response ends with ONE concrete next action the reader can do soon (e.g. "Next: ask the customer for their Okta metadata XML", "spike WorkOS in a branch"). FAIL if the ending is a generic offer ("Want me to…?", "I can sketch…", "let me know") with no concrete reader action, or lists several alternative next steps.
