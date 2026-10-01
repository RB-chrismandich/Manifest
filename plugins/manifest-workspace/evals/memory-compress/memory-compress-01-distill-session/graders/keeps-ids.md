---
type: llm
weight: 2
---
Pass only if ALL hold:
1. Output is just the entry: the header line followed by the entry text — no preamble ("Here's…"), no code fences, no commentary after.
2. The entry keeps every required fact: PR #412, commit a1b2c3d, `auth/refresh_token.py` (or refresh_token.py), `rotate_refresh()`, the `<`→`<=` boundary fix, tests 38→41 (or 41 passed / 3 new), and the `AUTH_SCHEMA_VERSION` 14→15 bump with its reason (`rotated_at` column).
3. It is compressed: roughly one or two sentences / ≤ ~60 words, not a paragraph-per-step narrative.
4. It contains no fact absent from the transcript.
