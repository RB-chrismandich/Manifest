---
type: llm
focus: last_message
weight: 0.5
---
Grade the final answer. PASS only if it suggests enumerating every `${VAR}` referenced in the provisioning files and checking each one is present in the Grafana container's environment (not only fixing PG_PASSWORD).
