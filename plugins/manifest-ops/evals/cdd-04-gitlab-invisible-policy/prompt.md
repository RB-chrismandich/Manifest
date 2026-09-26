---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@gitlab.com:acme/app.git`, and create these files exactly:

`.gitlab-ci.yml`:
```
include:
  - local: ci/test.yml
stages: [build, test]
build:
  stage: build
  image: node:22
  script:
    - npm ci
    - npm run build
```

`ci/test.yml`:
```
test:
  stage: test
  image: node:22
  script:
    - npm ci
    - npm test
```

`.eslintrc.json`:
```
{ "rules": { "max-len": ["warn", 140] } }
```

That scaffolding is the repo as it exists. Now, as a separate task:

This is a GitLab Ultimate, group-owned project. Our pipeline has a `policy-lint` job that fails on eslint `max-len: 80`, but nothing in this repo defines it, and `glab ci config compile` output contains no `policy-lint` job and no eslint invocation. Where is `policy-lint` coming from and how do we get the thresholds aligned?
