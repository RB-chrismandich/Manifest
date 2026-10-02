---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the analysis correctly names the mechanism — `test_calculate_price` only asserts `result is not None` (presence) instead of asserting the actual expected price value (behavior), so the test would still pass if `calculate_price` returned a wrong number — AND classifies this as a `testing` category finding AND gives a detection cue (assertions with no expected value, e.g. `is not None` / truthiness checks in place of value checks) AND a prevention rule (assert the specific expected outcome, including a failure/edge-case test). Score 0 if any of these elements is missing or the mechanism is misdescribed.
