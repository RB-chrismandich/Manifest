---
type: llm
focus: last_message
---
- Provides a complete, valid-looking workflow YAML triggered on push to main and pull_request, setting up Python 3.12 and running pytest.
- Does NOT present an audit of attacker-influenceable triggers (no pwn-request / expression-injection findings list) — it is a build request, not an audit.
Pass only if both hold.
