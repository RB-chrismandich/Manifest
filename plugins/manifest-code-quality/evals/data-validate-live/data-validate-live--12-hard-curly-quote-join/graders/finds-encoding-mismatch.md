---
type: llm
weight: 1
---
Score 1 only if the answer identifies that the registry's `"O'Brien Consulting"`
(straight apostrophe, U+0027) and the AP export's `"O’Brien Consulting"`
(curly/right single quotation mark, U+2019) are different Unicode characters
that look nearly identical when printed, and that `normalize()`'s
`strip().lower()` does nothing to fix this since the mismatch is neither
whitespace nor casing — it is a character-level encoding difference introduced
by the legacy system's Windows-1252-to-UTF-8 re-encoding. The answer must
recommend normalizing punctuation/quote characters on both sides before
comparing (e.g. mapping curly quotes/dashes to their ASCII equivalents, or
Unicode normalization) rather than just adding more whitespace or case
handling. Score 0 if the answer attributes the mismatch to case, whitespace, or
a typo, does not pinpoint the differing apostrophe character, or claims the
join should already work on this sample.
