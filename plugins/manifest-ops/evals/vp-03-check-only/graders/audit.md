---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It flags `FROM python:3.12` as a mutable tag without an immutable digest.
2. It gives the proposed fix: a digest-pinned form (`python:3.12.x@sha256:...`) or the exact way to obtain the digest (e.g. `docker manifest inspect` / the pin tool in check mode).
3. It does not claim to have modified the file.
