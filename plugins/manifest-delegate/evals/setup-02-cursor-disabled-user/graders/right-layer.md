---
type: llm
focus: last_message
---
Pass only if ALL of these hold:
1. The answer says cursor is NOT usable right now.
2. It identifies the user-level delegation config (`delegation.json`, or `delegation.yml`) as the blocker, and says enabling cursor there is sufficient.
3. It does NOT prescribe editing the workspace `services.yml` as the fix for this `disabled_user` row, and does NOT say workspace/admin access is required. (Mentioning `services.yml` only as a contingency for a different state, e.g. "if it then shows disabled_workspace…", is fine.)
4. It does not tell the user to reinstall or re-authenticate cursor (the state is a config disable, not an install/auth problem).
