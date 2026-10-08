#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@gitlab.com:acme/app.git
mkdir -p ci
cat > pyproject.toml <<'EOF'
[tool.ruff]
line-length = 120
EOF
cat > .gitlab-ci.yml <<'EOF'
include:
  - local: ci/lint.yml
stages: [lint, test]
EOF
cat > ci/lint.yml <<'EOF'
ruff:
  stage: lint
  image: python:3.12
  before_script:
    - pip install ruff==0.6.9
    - curl -sSfo ruff.toml https://gitlab.example.com/platform/lint-configs/-/raw/main/ruff.toml
  script:
    - ruff check .
EOF
