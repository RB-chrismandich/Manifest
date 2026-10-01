#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@gitlab.com:acme/app.git
cat > 'pyproject.toml' <<'EOF_0'
[tool.ruff]
line-length = 120
EOF_0
cat > '.gitlab-ci.yml' <<'EOF_1'
include:
  - local: ci/lint.yml
stages: [lint, test]
EOF_1
mkdir -p 'ci'
cat > 'ci/lint.yml' <<'EOF_2'
ruff:
  stage: lint
  image: python:3.12
  before_script:
    - pip install ruff==0.6.9
    - curl -sSfo ruff.toml https://gitlab.example.com/platform/lint-configs/-/raw/main/ruff.toml
  script:
    - ruff check .
EOF_2
