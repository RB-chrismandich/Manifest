---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
This is the only tool on our internal MCP server (bound to 127.0.0.1, token auth middleware in place). Anything to fix from a security standpoint?

```python
@mcp.tool()
def run_report(report_id: str) -> dict:
    try:
        conn = psycopg.connect(os.environ["REPORTS_DSN"])
        cur = conn.execute("SELECT sql FROM saved_reports WHERE id = %s", (report_id,))
        return {"rows": conn.execute(cur.fetchone()[0]).fetchall()}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
```
`REPORTS_DSN` includes the DB password. Responses land in the calling agent's transcript, which is stored in our shared logging stack.
