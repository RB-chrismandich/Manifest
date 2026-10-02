---
type: llm
focus: last_message
weight: 1
---
Verified behavior of the fixture: non-str input (None, bool, float, int) raises TypeError naming the field; anything that is not an ASCII base-10 digit string (e.g. "abc", "-1", Unicode digits) or is <= 0 raises ValueError naming the field and value; surrounding whitespace is stripped. Both failure paths propagate to the caller. Score 1 only if the answer does NOT report any Critical or High severity finding against this function. Info/Low advisories (docstring wording, an extra unit test, an upper bound on size) are fine. Score 0 if the answer reports a Critical/High defect such as missing type/boundary validation, a swallowed/unhandled exception, or an injection risk.
