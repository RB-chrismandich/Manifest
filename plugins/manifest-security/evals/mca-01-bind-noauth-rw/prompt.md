---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Please audit this MCP server for security issues:

```python
# notes_mcp/server.py
import os, sqlite3
from mcp.server.fastmcp import FastMCP

DB = os.environ.get("NOTES_DB", "/data/notes.db")
mcp = FastMCP("notes", host=os.environ.get("MCP_HOST", "0.0.0.0"), port=8765)

def _conn():
    c = sqlite3.connect(DB)
    c.executescript(open("schema.sql").read())   # CREATE TABLE IF NOT EXISTS ..., CREATE INDEX ...
    c.execute("INSERT OR IGNORE INTO meta(k, v) VALUES ('version', '3')")
    c.commit()
    return c

@mcp.tool(description="Read-only access to team notes.")
def search_notes(q: str) -> list[dict]:
    try:
        rows = _conn().execute("SELECT id, title FROM notes WHERE title LIKE ?", (f"%{q}%",)).fetchall()
        return [{"id": r[0], "title": r[1]} for r in rows]
    except Exception as exc:
        return [{"error": str(exc)}]

app = mcp.streamable_http_app()
```
Client config `.mcp.json`: `{"mcpServers": {"notes": {"type": "http", "url": "http://localhost:8765/mcp"}}}`
