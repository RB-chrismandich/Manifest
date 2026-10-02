---
type: llm
focus: last_message
---
- Explains that traffic to a Docker-published port is DNAT'd and traverses FORWARD (via DOCKER-USER), not INPUT — so these INPUT rules do nothing and the port is open to everyone, while the script prints false assurance.
- Provides corrected rules on the DOCKER-USER chain with the allowlisted source RETURN/ACCEPT ordered ABOVE the DROP.
- Recommends, where possible, not publishing the port (bind to an internal network / 127.0.0.1 or put Prometheus on a shared Docker network).
Pass only if all three hold.
