---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Our MCP server claims read-only DB access and we have a test proving it. Do you trust this?

```python
# server.py
def _conn():
    return sqlite3.connect(os.environ["DB_PATH"])   # production factory

@mcp.tool(description="Read-only query of inventory.")
def get_item(sku: str) -> dict: ...

# test_readonly.py
def test_tools_cannot_write(monkeypatch):
    ro = sqlite3.connect("file::memory:?mode=ro", uri=True)
    monkeypatch.setattr(server, "_conn", lambda: ro)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("CREATE TABLE x(a)")
```
