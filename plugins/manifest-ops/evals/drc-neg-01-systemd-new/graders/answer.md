---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gives a unit file with ExecStart (node /opt/api/server.js), User=api, Restart=on-failure, and an [Install] section.
2. It gives the daemon-reload / enable --now commands.
3. It does NOT describe a component-retirement verification procedure.
