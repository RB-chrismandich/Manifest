---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Our pen-test report flagged something in this Python data-access helper — can you refactor it and tell me what else needs fixing?

```python
def get_user(conn, username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    try:
        cur = conn.execute(query)
        return cur.fetchone()
    except:
        pass
```
