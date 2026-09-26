---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/app.git`, and create these files exactly:

`.yamllint`:
```
extends: default
rules:
  line-length:
    max: 150
    level: warning
```

`.github/workflows/lint.yml`:
```
name: lint
on: [push, pull_request]
jobs:
  yamllint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: yamllint
        run: yamllint --strict -d relaxed .
```

That scaffolding is the repo as it exists. Now, as a separate task:

yamllint passes locally but fails in GitHub Actions. CI output: 14 findings like `deploy/values.yaml:42:81 [warning] line too long (97 > 80 characters) (line-length)` and the step exits 2. Locally `yamllint .` shows nothing. What's going on and how should I fix it?
