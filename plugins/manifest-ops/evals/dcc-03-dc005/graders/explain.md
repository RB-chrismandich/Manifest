---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It explains that with no networks defined, all services share the default network, so the stateful db is on the same network as the publicly exposed web tier.
2. Its fix puts db on an `internal: true` network and puts web on BOTH the public network and that internal network.
3. It warns (explicitly or via the example) that isolating db without attaching web to the internal network would break web→db connectivity.
