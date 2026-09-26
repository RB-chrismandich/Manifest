---
type: llm
focus: {source: file, path: .github/workflows/ci.yml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It defines a Python job that installs the project (pip/uv with pyproject) and runs pytest.
2. Its Python version(s) respect requires-python `>=3.12,<3.13` (3.12 only; no 3.11 or 3.13 in the matrix).
3. It contains no Go, Node.js, or Terraform jobs.
4. It contains no hardcoded secrets/tokens (secrets, if any, come from `${{ secrets.* }}`).
