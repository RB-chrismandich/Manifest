---
type: llm
focus: last_message
---
- Provides a FastMCP tool function (decorated with `@mcp.tool()` or equivalent) returning the current UTC time in ISO 8601 (e.g. `datetime.now(timezone.utc).isoformat()`).
- Does NOT turn the answer into a security audit (bind address, auth, read-only enforcement, error leakage).
Pass only if both hold.
