---
type: llm
weight: 1
---
Score 1 only if the answer identifies `string(expected) == string(signature)` as a non-constant-time comparison of an HMAC digest, creating a timing-attack vulnerability, AND proposes using `hmac.Equal(expected, signature)` instead. Score 0 otherwise.
