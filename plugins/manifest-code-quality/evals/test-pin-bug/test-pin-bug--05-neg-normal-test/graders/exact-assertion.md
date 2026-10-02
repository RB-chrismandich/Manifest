---
type: llm
focus: last_message
weight: 1
---
`is_valid_slug` has no known bug and nothing is being deferred — this is a plain test-writing request. Score 1 if the answer writes ordinary exact assertions, e.g. `assert is_valid_slug("my-post-title") is True` and `assert is_valid_slug("My Post") is False`, with no alternation/tolerance language, no mention of a "known bug," and no talk of a future fix changing the expected value. Score 0 if the answer treats this as pinning known-buggy behavior (e.g. hedges the expected value, or discusses tolerating a future fix) when there is nothing to pin.
