---
type: llm
focus: last_message
---
- Flags that `name` comes from model output and reaches `mkdir`/`write_text` unguarded.
- Explains BOTH escapes: an absolute `name` makes `SKILLS / name` discard the base entirely, and `../` segments escape the base.
- Notes that `[^\n]+` is too permissive and recommends a strict slug allowlist (e.g. `^[a-z0-9][a-z0-9-]{0,63}$`).
- Recommends a containment check (`resolve()` + `relative_to(base.resolve())`) in ADDITION to the allowlist.
- Identifies indirect prompt injection via ingested web pages/transcripts as the way an attacker controls `name`.
Pass only if all five hold.
