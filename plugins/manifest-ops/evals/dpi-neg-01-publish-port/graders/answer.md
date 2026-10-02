---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It shows `ports: ["3000:3000"]` (host:container) in the service.
2. It mentions the app must bind 0.0.0.0 inside the container (not 127.0.0.1).
3. It does NOT prescribe a throwaway-container internal-network probe.
