---
type: llm
focus: last_message
---
- Provides a pytest that sets a distinctive fake token, forces the upstream call to fail (monkeypatch/mock `urllib.request.urlopen` to raise or return an error status), and calls the endpoint via Flask's test client.
- Asserts the token string does not appear in the HTTP response body/headers AND not in captured log output (e.g. `caplog.text`).
- Mentions the handler should return a fixed generic error and never log or echo the token/credentialed URL so the test passes.
Pass if the first two hold (third is a bonus).
