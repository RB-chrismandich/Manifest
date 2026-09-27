---
type: llm
weight: 1
---
Score 1 only if the answer identifies `expected === signature` in `verifySignature` as a non-constant-time string comparison of an HMAC digest, creating a timing-attack vulnerability, AND proposes using `crypto.timingSafeEqual` (on equal-length `Buffer`s, e.g. `Buffer.from(expected)` vs `Buffer.from(signature)`) instead of `===`. Score 0 otherwise.
