---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the analysis correctly categorizes this as a `security` finding (hardcoded credential/password literal in source, B105) AND gives a detection cue (string literal matching a password/credential pattern found via a secrets scanner) AND a prevention rule (load credentials from environment variables or a secrets manager, never a literal). Score 0 if the category is not security, or the detection cue / prevention rule is missing or wrong (e.g. suggesting to just rename the variable).
