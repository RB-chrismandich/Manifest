---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `normalize()` only strips leading and
trailing whitespace and does nothing about case differences or
punctuation/wording variants, so against this sample: "Acme Corp." (trailing
period) fails to match the registry's "Acme Corp", and "SMITH & JONES LLP" fails
to match "Smith and Jones LLP" (case difference and "&" vs "and") — causing the
near-zero match rate. It must recommend normalizing more aggressively on both
sides of the join (e.g. lowercasing, stripping trailing punctuation, and/or
normalizing "&"/"and") rather than just whitespace-stripping. Score 0 if it does
not name the case/punctuation normalization gap as the cause of the low match
rate.
