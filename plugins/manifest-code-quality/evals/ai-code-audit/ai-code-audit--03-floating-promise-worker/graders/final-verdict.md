---
type: llm
focus: last_message
weight: 1
---
The skill's verdict rule: any verified critical → BLOCKED; else any verified high tagged `security` or `error-handling` → BLOCKED; else any verified high → NEEDS_REVIEW; else APPROVED. The un-awaited promise in the worker loop is a high finding that may legitimately be tagged `async-state` (→ NEEDS_REVIEW) or `error-handling` because rejections are silently lost (→ BLOCKED). Identify the answer's FINAL verdict (ignore negated/hypothetical mentions such as "not BLOCKED"). Score 1 only if the final verdict is consistent with this rule for the tag/severity the answer itself assigns: NEEDS_REVIEW with an async-state (or untagged) high finding, or BLOCKED with the finding explicitly tagged error-handling/security or rated critical. Score 0 if the verdict is APPROVED, contradicts the answer's own tagging (e.g. BLOCKED for a finding it tags async-state/high), or no clear final verdict is given.
