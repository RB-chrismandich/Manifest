---
type: llm
focus: {source: file, path: .gitlab-ci.yml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It defines Go jobs (e.g. `go vet`, `go test ./...`) using a Go 1.22 image/toolchain.
2. It contains no Python, Node.js, or Terraform jobs.
3. It uses GitLab CI syntax (stages/jobs/image/script), not GitHub Actions syntax.
