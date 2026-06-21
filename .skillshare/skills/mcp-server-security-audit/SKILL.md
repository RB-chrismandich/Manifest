---
name: mcp-server-security-audit
description: Audit an HTTP-exposed MCP server (FastMCP/streamable-http) reading from a database — checks bind address, authentication, read-only enforcement at the connection layer, and error-detail leakage.
---
# MCP Server Security Audit

MCP servers that expose tools over HTTP are trust boundaries. Tools are typically invoked by an LLM client whose transcript persists the responses, so both the network exposure and the response contents matter. Walk these checks in order.

1. **Bind address vs. documented client config.** Find the host the server binds (`host=`, `MCP_HOST`, uvicorn config). A default of `0.0.0.0` accepts connections from every interface (LAN, peer containers, port-forwards). If the companion client config (`.mcp.json`) points at `http://localhost:...`, the intended trust boundary is local-only — default to `127.0.0.1` and require an explicit env override to expose externally. Flag a `0.0.0.0` default with no auth as **high severity**.

2. **Authentication layer.** Grep the server module for `auth|token|Bearer|verify|api_key|allowlist`. If none exists in front of `streamable_http_app()` (or equivalent), every tool is unauthenticated. For any externally reachable bind, require a token/Authorization middleware or a Unix-socket transport, and confirm the threat model is documented.

3. **Read-only contract enforced at the connection layer, not just claimed.** A description string saying "read-only access" is a trust signal, not a control. Trace the per-request connection factory (`_conn()`/`connect()`). If it opens the DB in default read-write mode and/or runs schema-apply/migrations (`executescript`, `ALTER TABLE`, `CREATE INDEX`, `INSERT OR IGNORE`, `commit()`) on **every** request, the contract is violated and an unauthenticated caller triggers DDL/DML per call. Require: open read-only (`sqlite3.connect("file:...?mode=ro", uri=True)` or backend equivalent), and run any migrations **once at startup** on a separate read-write connection that is closed before serving.

4. **Test-path honesty.** Check whether the read-only / no-write unit tests patch the connection factory to inject a pre-built in-memory connection. If so, they bypass the production `connect()` path and prove nothing about the deployed write-capability. Recommend a test that exercises the real factory.

5. **Error detail leakage.** Find the tool error handlers. Returning `str(exc)` to the caller leaks DB paths, table/column names, and SQL fragments — and persists them into the client's LLM transcript and logs. Require logging the full exception server-side with a request id and returning a generic `{"error": "...", "request_id": rid}` to the caller, applied consistently across all tools.
