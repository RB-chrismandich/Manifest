---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Audit this MCP server; tell me if anything is high severity.

```python
DB = os.environ["INV_DB"]
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
mcp = FastMCP("inventory", host=HOST, port=8770)

def migrate_once():
    with sqlite3.connect(DB) as rw:
        rw.executescript(SCHEMA)
    # rw closed before serving

def _conn():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

@mcp.tool(description="Read-only inventory lookup.")
def lookup(sku: str) -> dict:
    rid = uuid.uuid4().hex
    try:
        row = _conn().execute("SELECT sku, qty FROM items WHERE sku = ?", (sku,)).fetchone()
        return {"sku": row[0], "qty": row[1]} if row else {}
    except Exception:
        log.exception("lookup failed rid=%s", rid)
        return {"error": "internal error", "request_id": rid}

if __name__ == "__main__":
    migrate_once()
    mcp.run(transport="streamable-http")
```
Only local agents on the same host use it; `.mcp.json` points at http://localhost:8770/mcp.
