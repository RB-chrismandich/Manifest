---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
The workflow must include a Python 3.12 job that installs the project and exercises it with pytest and/or ruff. It must also validate Terraform with formatting checks and `terraform validate`; initialize with `-backend=false` or an equivalent arrangement so validation does not depend on AWS credentials. Do not add Go or Node jobs, and do not embed cloud credentials.
