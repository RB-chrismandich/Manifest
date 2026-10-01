#!/usr/bin/env bash
set -euo pipefail
git init -q
git remote add origin git@gitlab.com:acme/app.git
cat > '.gitlab-ci.yml' <<'EOF_0'
include:
  - local: ci/test.yml
stages: [build, test]
build:
  stage: build
  image: node:22
  script:
    - npm ci
    - npm run build
EOF_0
mkdir -p 'ci'
cat > 'ci/test.yml' <<'EOF_1'
test:
  stage: test
  image: node:22
  script:
    - npm ci
    - npm test
EOF_1
cat > '.eslintrc.json' <<'EOF_2'
{ "rules": { "max-len": ["warn", 140] } }
EOF_2
