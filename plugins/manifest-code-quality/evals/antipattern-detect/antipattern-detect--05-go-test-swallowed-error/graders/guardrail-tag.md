---
type: llm
focus: last_message
weight: 0.5
---
The skill requires exactly ONE guardrail-category tag from {arch, async-state, error-handling, security, dependency, iteration}. Score 1 only if the drafted knowledge-base entry contains an explicit guardrail tag field (e.g. `guardrail: error-handling`, `tags: [error-handling, ...]` where it is the only guardrail value, or a "Guardrail tag:" line) with EXACTLY ONE guardrail value, and that value is `error-handling`. Using the word only as the finding's category, with no separate guardrail tag field, scores 0. Zero guardrail tags, more than one, or a different one scores 0.
