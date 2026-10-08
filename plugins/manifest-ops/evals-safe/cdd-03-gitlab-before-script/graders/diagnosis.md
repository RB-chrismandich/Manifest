---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer follows the `.gitlab-ci.yml` include to `ci/lint.yml`, then explains how the `before_script` downloads a `ruff.toml` whose 88-column setting takes precedence over the repository's 120-column `pyproject.toml` setting. It must identify configuration drift as the cause. It must recommend removing/avoiding that override or explicitly selecting the project config, unless the shared 88-column policy is intentionally adopted; do not present source reformatting alone as the diagnosis.
