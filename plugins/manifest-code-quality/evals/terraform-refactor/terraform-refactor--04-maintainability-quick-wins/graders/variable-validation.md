---
type: llm
weight: 1
---
`variable "environment"` is declared but never referenced, and it has no description or validation. Score 1 only if the answer flags this variable AND gives a sound fix: either remove it / wire it into the resources (e.g. tags or names), or add a `description` and a `validation` block constraining it to the allowed environments. Score 0 if the variable is not mentioned.
