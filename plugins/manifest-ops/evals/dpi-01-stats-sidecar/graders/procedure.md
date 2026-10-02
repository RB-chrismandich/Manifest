---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It explains the service has no published port so the host cannot reach it; it is only reachable from containers on the `backend` network.
2. It runs a throwaway container attached to the project-prefixed network (`homelab_backend`) with `--rm`, probing `http://controld-stats:8080/summary` via Docker DNS.
3. It prints/parses the response body (e.g. decoded JSON), not just checks that the port is open or the status is 200.
4. It does NOT recommend publishing a port or adding a reverse-proxy route as the primary way to test.
