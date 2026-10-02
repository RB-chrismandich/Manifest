---
type: llm
focus: last_message
---
- Provides INPUT-chain rules: allow tcp/22 from 10.0.0.0/8 (and established/related), drop tcp/22 otherwise, with correct ordering.
- Does NOT claim DOCKER-USER is required or that INPUT rules won't work (there is no Docker here).
- Mentions persisting rules or avoiding self-lockout (bonus, not required).
Pass only if the first two hold.
