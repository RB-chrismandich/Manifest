---
type: llm
weight: 1
---
Score 1 only if the answer flags `&http.Client{}` in `NewClient` as missing a `Timeout` field, meaning requests to the provider can hang indefinitely, AND proposes setting an explicit timeout (e.g. `&http.Client{Timeout: 10 * time.Second}`). Score 0 otherwise.
