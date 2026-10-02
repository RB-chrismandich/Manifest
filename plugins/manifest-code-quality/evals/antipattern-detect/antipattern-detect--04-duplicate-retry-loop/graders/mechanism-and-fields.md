---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the analysis correctly names the mechanism — the same ~12-line exponential-backoff retry loop is hand-copied into three files (retry.js already exists as a shared module, yet processPayment.js and syncInventory.js reimplement it instead of importing it) — AND classifies this as a `duplication` category finding AND gives a detection cue (10+ line near-identical blocks appearing more than once / near-identical helper names) AND a prevention rule (search for an existing helper before writing one; consolidate to the one in src/utils/retry.js and import it everywhere). Score 0 if any element is missing or misdescribed.
