---
type: llm
focus: {source: file, path: .gitlab-ci.yml}
weight: 1
---
Assess `.gitlab-ci.yml`: it must define Go validation (for example, `go vet` and `go test ./...`) using a Go 1.22 image or toolchain. It must be valid GitLab CI structure with stages/jobs, image, and script rather than GitHub Actions syntax. It must not add Python, Node.js, or Terraform jobs.
