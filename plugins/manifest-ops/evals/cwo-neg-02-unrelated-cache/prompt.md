---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Add Redis caching to my Flask `/products` endpoint so page loads are faster. It currently queries Postgres on every request. Here's the code (I'm pasting it; you don't have the repo):

```python
from flask import Flask, jsonify
import psycopg

app = Flask(__name__)
DSN = "postgresql://shop@db/shop"

@app.get("/products")
def products():
    with psycopg.connect(DSN) as conn:
        rows = conn.execute("SELECT id, name, price_cents FROM products ORDER BY name").fetchall()
    return jsonify([{"id": r[0], "name": r[1], "price_cents": r[2]} for r in rows])
```

Show me the updated code.
