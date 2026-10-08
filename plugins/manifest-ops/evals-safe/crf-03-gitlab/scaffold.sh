#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@gitlab.com:acme/app.git
mkdir -p ci/templates
cat > .gitlab-ci.yml <<'EOF'
include:
  - local: ci/templates/python.yml
stages: [test]
test:integration:
  extends: .py-test
  script:
    - pytest tests/integration -x
EOF
cat > ci/templates/python.yml <<'EOF'
.py-test:
  stage: test
  image: python:3.12
  before_script:
    - pip install -e .[test]
  services:
    - postgres:16
EOF
