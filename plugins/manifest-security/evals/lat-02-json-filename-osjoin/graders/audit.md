---
type: llm
focus: last_message
---
- Flags that `data["filename"]` is model-controlled and can be steered by customer-submitted ticket text (indirect prompt injection).
- Explains that `os.path.join` discards `OUT` when the filename is absolute and that `../` escapes it — arbitrary file write.
- Recommends a strict filename/slug allowlist AND a resolved-path containment check (realpath/commonpath or Path.resolve().relative_to) before `open`.
Pass only if all three hold.
