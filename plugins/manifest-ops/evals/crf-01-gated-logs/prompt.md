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
on: [pull_request]
jobs:
  lint-and-generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Lint
        run: make lint
      - name: Verify generated files
        run: make generate && git diff --exit-code
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make e2e
```

`Makefile`:
```
lint:
	@echo lint
generate:
	@echo generate
e2e:
	@echo e2e
```

That scaffolding is the repo as it exists. Now, as a separate task:

GitHub Actions run 9912345678 on my PR: the `lint-and-generate` job has a red X, but `gh run view 9912345678 --log-failed` just says "run 9912345678 is still in progress; logs will be available when it is complete". The e2e job will keep running for another ~40 minutes. How do I find out what failed and reproduce it right now?
