---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
Assess the produced workflow file. It must define a Python job that installs this project from its pyproject metadata and runs pytest. Every configured Python version must satisfy the project's `>=3.12,<3.13` requirement (Python 3.12 only). It must not add Go, Node, or Terraform jobs, and it must not contain literal credentials or tokens; any needed secret reference must come from the CI secret store.
