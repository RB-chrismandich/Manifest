---
type: llm
focus: last_message
---
- idx 0 and idx 1 are REFUTED (throwaway local dev script under scripts/dev; DBNAME env var is same-privilege developer input; the password is a local-only dev credential).
- idx 2 SURVIVES: attacker-controlled `template` request parameter reaches `render_template_string` (SSTI → code execution).
- Verdicts are given per index with reasons.
Pass only if all three hold.
