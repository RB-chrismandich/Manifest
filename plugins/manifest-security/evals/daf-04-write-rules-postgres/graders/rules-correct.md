---
type: llm
focus: last_message
---
- Uses the DOCKER-USER chain (and explains INPUT would not apply to Docker-published ports).
- Orders the allow (RETURN/ACCEPT for -s 10.0.0.5) above the DROP for dport 5432, and explains the ordering (e.g. `-I` prepends).
- Suggests the stronger alternative of not publishing 5432 at all (both containers on an unexposed shared Docker network, no `-p`) when the client allows it. Suggesting a host-IP bind (`-p <ip>:5432:5432`) as a REPLACEMENT for the source filter does NOT satisfy this — a host-IP bind still publishes the port to every host that can reach that interface.
Pass only if all three hold.
