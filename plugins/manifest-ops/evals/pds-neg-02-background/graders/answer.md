---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It gives options like `nohup ... &`, tmux/screen, or a systemd service/`systemd-run`, with output redirection.
2. It does NOT prescribe stall diagnosis (py-spy, lsof, resource-signature classification).
