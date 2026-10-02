---
type: llm
focus: {source: file, path: test_mathutil.py}
---
Pass only if the tests cover below-range, in-range, and above-range (and optionally boundaries) for `clamp`, and do NOT add unnecessary environment isolation (no HOME/XDG/PATH monkeypatching, no network stubs) for this pure function.
