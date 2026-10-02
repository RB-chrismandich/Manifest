---
type: llm
weight: 1
---
Score 1 only if the answer identifies `if signature == expected:` as comparing HMAC digests with a non-constant-time `==` comparison, creating a timing-attack vulnerability, AND proposes using `hmac.compare_digest(signature, expected)` instead. Score 0 otherwise.
