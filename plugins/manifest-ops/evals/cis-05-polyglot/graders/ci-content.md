---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It has a Python job (install + pytest/ruff) on Python 3.12.
2. It has a Terraform job running at least `terraform fmt -check` and `terraform validate` (init with `-backend=false` or equivalent so no AWS credentials are needed for validation).
3. It contains no Go or Node.js jobs.
4. It contains no hardcoded cloud credentials.
