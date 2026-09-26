---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@gitlab.com:acme/app.git`, and create these files exactly:

`pyproject.toml`:
```
[tool.ruff]
line-length = 120
```

`.gitlab-ci.yml`:
```
include:
  - local: ci/lint.yml
stages: [lint, test]
```

`ci/lint.yml`:
```
ruff:
  stage: lint
  image: python:3.12
  before_script:
    - pip install ruff==0.6.9
    - curl -sSfo ruff.toml https://gitlab.example.com/platform/lint-configs/-/raw/main/ruff.toml
  script:
    - ruff check .
```

That scaffolding is the repo as it exists. Now, as a separate task:

GitLab CI: ruff fails with E501 at 88 columns, but locally ruff is clean. The shared `ruff.toml` that CI downloads sets `line-length = 88`. Why does CI disagree with my pyproject, and what should I change?
