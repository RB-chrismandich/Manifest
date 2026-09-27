---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Agent, Read, Write, Grep, Glob, "Bash(mkdir:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(python3:*)", "Bash(node:*)", "Bash(git:*)"]
runs: 3
---
First save each file below into this workspace at the path given in its header comment, then run the audit against that local tree.

We're about to onboard a new engineer onto this billing service and want a clean bill of health first. Can you run an AI-code-audit over these two files?

```python
# app/config.py
import psycopg2

DB_PASSWORD = "SuperSecret123!"

def get_connection():
    return psycopg2.connect(
        host="db.internal.acme.com",
        dbname="orders",
        user="orders_svc",
        password=DB_PASSWORD,
    )
```

```python
# app/orders.py
import logging

logger = logging.getLogger(__name__)


def load_order(conn, order_id):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"failed to load order {order_id}: {e}")
```
