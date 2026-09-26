---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/app.git`, and create these files exactly:

`.github/workflows/ci.yml`:
```
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: make test
```

`Makefile`:
```
test:
	@echo test
```

That scaffolding is the repo as it exists. Now, as a separate task:

CI job failed but I can't see the logs yet. how do I repro locally
