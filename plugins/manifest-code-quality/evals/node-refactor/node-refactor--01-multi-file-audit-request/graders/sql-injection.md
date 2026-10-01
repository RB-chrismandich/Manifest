---
type: llm
weight: 1
---
Score 1 only if the answer flags the template literal `` `SELECT * FROM users WHERE email = '${email}'` `` in `src/db.ts` as a SQL injection vulnerability, rates it Critical, AND proposes a parameterized-query fix (e.g. `pool.query("SELECT * FROM users WHERE email = $1", [email])`). Score 0 otherwise.
