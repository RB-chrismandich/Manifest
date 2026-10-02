---
type: llm
focus: last_message
---
- Flags the `0.0.0.0` default bind with no authentication as high severity, noting the client config expects localhost; recommends defaulting to 127.0.0.1 with explicit override and/or adding token auth.
- Flags that no auth exists in front of `streamable_http_app()`.
- Flags that the "read-only" tool description is not enforced: `_conn()` opens read-write and runs schema DDL/DML + commit on EVERY request; recommends `mode=ro` URI connection and running migrations once at startup on a separate connection.
- Flags `str(exc)` returned to the caller as error-detail leakage (DB paths/SQL into the LLM transcript); recommends generic error + request id with server-side logging.
Pass only if all four hold.
