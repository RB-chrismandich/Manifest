---
type: llm
focus: last_message
weight: 1
---
Beyond the tolerant length assertion, score 1 only if the answer separately anchors a real invariant that holds under both the current and fixed behavior — e.g. asserting the result ends with `"..."`, or that the non-ellipsis prefix of the result (`"hello"` or `"he"`) is itself a prefix of the original string `"hello world"`, checked as its own assertion distinct from the tolerant length/value check. Score 0 if there is no separate invariant assertion, or if the "invariant" is just a restatement of the same alternation with nothing independently verified.
