---
type: llm
focus: last_message
weight: 1
---
The user is fixing this bug right now, not deferring it, so there is nothing to pin. Score 1 only if the answer (a) actually fixes `round_price` so it rounds instead of truncates (e.g. `round(cents / 100)` or `(cents + 50) // 100`), AND (b) asserts the single correct value `round_price(1995) == 20` as a plain exact equality, with no alternation, no tolerance for the old value `19`, and no "won't break when fixed later" framing. Score 0 if the test still accepts `19` as a valid outcome, if the bug is left unfixed, or if the answer hedges the expected value as if the fix were still pending.
