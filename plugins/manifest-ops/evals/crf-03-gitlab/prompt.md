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
  - local: ci/templates/python.yml
stages: [test]
test:integration:
  extends: .py-test
  script:
    - pytest tests/integration -x
```

`ci/templates/python.yml`:
```
.py-test:
  stage: test
  image: python:3.12
  before_script:
    - pip install -e .[test]
  services:
    - postgres:16
```

That scaffolding is the repo as it exists. Now, as a separate task:

GitLab MR pipeline: the `test:integration` job failed, but its job log in the UI is truncated ("Job's log exceeded limit") so I can't see the error. How do I reproduce this failure locally?
