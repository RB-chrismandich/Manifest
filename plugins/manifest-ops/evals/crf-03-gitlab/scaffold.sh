#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@gitlab.com:acme/app.git
cat > '.gitlab-ci.yml' <<'EOF_0'
include:
  - local: ci/templates/python.yml
stages: [test]
test:integration:
  extends: .py-test
  script:
    - pytest tests/integration -x
EOF_0
mkdir -p 'ci/templates'
cat > 'ci/templates/python.yml' <<'EOF_1'
.py-test:
  stage: test
  image: python:3.12
  before_script:
    - pip install -e .[test]
  services:
    - postgres:16
EOF_1
