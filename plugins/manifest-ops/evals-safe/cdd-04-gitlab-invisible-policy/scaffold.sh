#!/bin/sh
set -eu
umask 077
git init --quiet --template= .
git remote add origin git@gitlab.com:acme/app.git
mkdir -p ci
cat > .gitlab-ci.yml <<'EOF'
include:
  - local: ci/test.yml
stages: [build, test]
build:
  stage: build
  image: node:22
  script:
    - npm ci
    - npm run build
EOF
cat > ci/test.yml <<'EOF'
test:
  stage: test
  image: node:22
  script:
    - npm ci
    - npm test
EOF
cat > .eslintrc.json <<'EOF'
{ "rules": { "max-len": ["warn", 140] } }
EOF
