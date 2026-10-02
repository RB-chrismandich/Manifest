---
type: llm
weight: 1
---
Score 1 only if the answer flags `exec.Command("sh", "-c", "run-script "+scriptName)` in `internal/auth/script.go` as command injection because `scriptName` is concatenated unsanitized into a shell command string, rates it Critical, AND proposes a fix such as calling the binary directly with arguments (`exec.Command("run-script", scriptName)`, no `sh -c`) or validating/allow-listing `scriptName`. Score 0 otherwise.
