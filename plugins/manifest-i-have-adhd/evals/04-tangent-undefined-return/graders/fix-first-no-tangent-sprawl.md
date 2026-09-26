---
type: llm
focus: last_message
weight: 1
---
Score PASS only if ALL hold:
1. The response leads with the fix for the asked question: the function has no `return` statement (e.g. `return total`).
2. Other issues (global mutable `total`, `var`, could use reduce) are EITHER omitted, OR mentioned only after the fix as one brief separate offer/question — not woven into the main explanation and not as a list of several unrequested refactors.
3. The response does not contain a "by the way"/"also note"-style sidebar in the middle of the fix.
Otherwise FAIL.
