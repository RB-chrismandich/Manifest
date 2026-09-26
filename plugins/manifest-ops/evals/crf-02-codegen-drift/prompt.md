---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/app.git`, and create these files exactly:

`.github/workflows/checks.yml`:
```
name: checks
on: [pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Verify generated files are up to date
        run: |
          make generate
          git diff --exit-code
      - name: Unit tests
        run: go test ./...
```

`Makefile`:
```
generate:
	go generate ./...
```

That scaffolding is the repo as it exists. Now, as a separate task:

The jobs API shows for job `checks`: steps 1-3 completed success, step 4 `Verify generated files are up to date` completed failure, step 5 `Unit tests` skipped. Tests pass locally. What's the failure and how do I fix it?
