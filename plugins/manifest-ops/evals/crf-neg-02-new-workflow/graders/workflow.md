---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It provides a workflow YAML with a pull_request trigger, actions/setup-go, `go test ./...`, and golangci-lint.
2. It does NOT describe a failed-run reproduction procedure (jobs API, headSha pinning).
