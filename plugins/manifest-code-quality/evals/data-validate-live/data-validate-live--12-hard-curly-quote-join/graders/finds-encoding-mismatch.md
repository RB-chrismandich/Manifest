---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the registry's `"O'Brien Consulting"`
(straight apostrophe, U+0027) and the AP export's `"O’Brien Consulting"`
(curly/right single quotation mark, U+2019) are different Unicode characters
that look nearly identical when printed, and that `normalize()`'s
`strip().lower()` does nothing to fix this since the mismatch is neither
whitespace nor casing — the two source values simply use different apostrophe
code points. (Do not require any claim about how the curly quote got there.) The answer must
recommend explicit punctuation/quote folding on both sides before comparing —
mapping curly quotes/dashes to their ASCII equivalents (a translate/replace or
equivalent transform) — rather than just adding more whitespace or case
handling. Plain Unicode normalization (NFC/NFD/NFKC/NFKD) does NOT map U+2019 to
U+0027, so proposing normalization alone does not satisfy this rubric. Score 0
if the answer attributes the mismatch to case, whitespace, or a typo, does not
pinpoint the differing apostrophe character, proposes only Unicode
normalization, or claims the join should already work on this sample.
