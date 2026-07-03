---
name: security-harden-proxy
description: Use when building a service or sidecar that calls an authenticated upstream API (Bearer token, API key) and relays results, to prevent the credential or full URL from leaking into logs or client responses
---
# Secret-Safe Upstream Proxy

A service that authenticates to an upstream and returns aggregated/proxied data can leak the token through exception tracebacks, error responses, or logs. Build it so the secret never escapes.

1. **Keep the token in one place** — read it once from the environment; never embed it in returned data, never echo the constructed URL (which may carry it as a query param) back to the client.
2. **Wrap every upstream call and sever the exception chain** — `urllib`/HTTP-client errors carry the request object (with its `Authorization` header) in their traceback. Re-raise a clean error that drops the context:
   ```python
   try:
       with _get(url, token, accept) as resp:
           ...
   except Exception:
       raise RuntimeError("upstream request failed") from None  # `from None` discards the chained context
   ```
3. **Return a generic error to clients** — on failure, send a fixed status + opaque message (e.g. `502 "upstream error"`); never include the exception text, URL, or headers in the HTTP response body.
4. **Override the log formatter to log message-only** — ensure the access/error logger prints just the human message, not the request line or headers, and route it to stdout for container capture.
5. **Stream and cap untrusted payloads** — when the upstream returns a large/unbounded body, iterate it line-by-line and abort past a byte cap rather than buffering the whole response, keeping memory bounded regardless of upstream size.
6. **Keep it internal-only** — bind the service to the private network/IP, never expose it through the reverse proxy, since it holds a privileged credential.
7. **Add a review/test that asserts no leak** — a unit test that forces an upstream failure and asserts the token string does not appear in the raised message or response.
