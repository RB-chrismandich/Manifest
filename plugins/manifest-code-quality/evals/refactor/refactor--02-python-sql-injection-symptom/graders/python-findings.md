---
type: llm
weight: 1
---
Score 1 only if the answer gives Python-specific findings: it identifies BOTH (1) the f-string `f"SELECT * FROM users WHERE username = '{username}'"` as a SQL-injection vulnerability, recommending a parameterized query (e.g. `conn.execute("SELECT * FROM users WHERE username = ?", (username,))` or the driver's placeholder syntax), AND (2) the bare `except: pass` as silently swallowing every exception, with a fix that keeps the failure visible to the caller — catch a specific exception and re-raise (optionally wrapped/after logging), return an explicit failure result the caller must check, or route it to a central handler. Score 0 if either finding is missing, if the error fix only logs and then continues/returns a default, or if the advice is generic/IaC/shell instead of Python-specific.
