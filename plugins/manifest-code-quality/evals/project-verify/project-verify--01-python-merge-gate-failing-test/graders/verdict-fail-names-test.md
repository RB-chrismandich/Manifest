---
type: llm
focus: last_message
weight: 1
---
The skill labels a non-zero test exit as WARN in its exit-code table but as FAIL in its worked example, so grade what the user needs, not the label. Score 1 only if the answer makes clear the quality gate did NOT pass because a test fails (FAIL, "do not merge", "CI will stay red", or a WARN that explicitly says the failing test must be fixed before merging), AND names `test_add` in `test_app.py` as the failing test (or states that `add(2, 3)` returns 5 while the test expects 6). Score 0 if it reports PASS, presents the result as safe to merge, fails to name the specific failing test, or blames a different test/file.
