---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It says to run a throwaway container attached to the same Docker network (`docker run --rm --network <net> ...`).
2. It addresses the service by its compose service name (Docker DNS) and in-network port.
3. It checks the response body, and does NOT make publishing a port the primary recommendation.
