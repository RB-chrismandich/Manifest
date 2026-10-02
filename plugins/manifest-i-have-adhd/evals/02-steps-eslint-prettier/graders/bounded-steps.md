---
type: llm
focus: last_message
weight: 1
---
Score PASS only if ALL hold:
1. The setup is presented as a numbered list of steps.
2. The top-level numbered list has at most 5 items, OR it is explicitly split into groups like "do now" vs "later"/"optional".
3. Each step is one bounded action (no step chains three or more distinct actions with "and then").
4. The response opens with an action or the first step, not an introductory paragraph about what ESLint/Prettier are.
Otherwise FAIL.
