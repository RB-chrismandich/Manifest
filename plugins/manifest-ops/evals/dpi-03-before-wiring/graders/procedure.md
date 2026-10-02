---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It recommends probing the internal service standalone BEFORE wiring Grafana, to separate 'is the service healthy / returning valid data' from 'is the Grafana integration correct'.
2. It gives a throwaway container probe on `obs_backend` hitting `http://metrics-api:9000/api/v1/series`.
3. It asserts on the payload shape (parsed JSON fields), not just an open port.
