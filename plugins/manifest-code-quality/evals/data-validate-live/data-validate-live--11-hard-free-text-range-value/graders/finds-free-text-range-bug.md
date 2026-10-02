---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `parse_amount` crashes (`ValueError`)
on `"Over $1,000,000"` because the regex `[,$]` only strips commas and dollar
signs, leaving the word "Over" and a space, which `float()` rejects — AND
explains that the fix is not simply to strip more punctuation/words down to a
bare number, because "Over $1,000,000" is a disclosed threshold, not an exact
amount, so silently coercing it to `1000000.0` would misrepresent the real
figure. The answer must recommend handling this class of value distinctly
(e.g. a dedicated range/threshold parser, flagging it instead of folding it
into the exact total, or storing a lower-bound/midpoint explicitly) rather than
treating it as an ordinary numeric string once cleaned. Score 0 if the answer
only proposes a broader regex/strip to force a float out of the string without
addressing that the resulting number would misrepresent a threshold value, or
if it claims the code handles the live sample correctly.
