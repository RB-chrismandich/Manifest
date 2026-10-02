---
type: llm
focus: last_message
---
- Flags that the full URL containing `api_key` is logged (credential in logs).
- Flags that the error response returns both `str(e)` and `url` to the client, leaking the API key (requests exceptions also embed the URL).
- Recommends: never echo the URL/exception to clients (fixed generic 502) and never log the credentialed URL (log message-only or redact).
- Bonus (not required): moving the key to a request header, and URL-encoding / passing `city` via `params=`.
Pass only if the first three hold.
