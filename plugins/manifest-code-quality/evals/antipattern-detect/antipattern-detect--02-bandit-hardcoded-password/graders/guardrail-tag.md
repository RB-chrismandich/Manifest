---
type: llm
focus: last_message
weight: 0.5
---
Score 1 only if the drafted knowledge-base entry contains an explicit guardrail tag field (e.g. `guardrail: security`, `tags: [security]`, or a "Guardrail tag:" line) with EXACTLY ONE guardrail value, and that value is `security`. Mentioning "security" only as the finding's category, with no separate guardrail tag, scores 0. Zero or multiple guardrail tags score 0.
