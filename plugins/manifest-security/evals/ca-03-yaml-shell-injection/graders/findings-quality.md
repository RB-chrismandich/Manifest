---
type: llm
focus: last_message
---
- Flags `yaml.load(..., Loader=yaml.Loader)` on request data as unsafe deserialization; recommends `yaml.safe_load`.
- Flags command injection: `spec['from']`/`spec['to']` from the request interpolated into a `shell=True` command; recommends an argument list without shell and an allowlist of formats.
- Both rated critical/high with a location.
Pass only if all three hold.
