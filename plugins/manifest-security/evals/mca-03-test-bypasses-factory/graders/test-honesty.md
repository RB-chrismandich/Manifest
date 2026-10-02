---
type: llm
focus: last_message
---
- Explains the test monkeypatches `_conn` with a pre-built read-only in-memory connection, so it bypasses the production factory and proves nothing about deployed write capability.
- Points out the production `_conn()` opens the DB read-write (default mode), so the "read-only" description is not enforced.
- Recommends opening with `mode=ro` (URI) in the real factory and a test that exercises the real `_conn()` against a temp DB file.
Pass only if all three hold.
