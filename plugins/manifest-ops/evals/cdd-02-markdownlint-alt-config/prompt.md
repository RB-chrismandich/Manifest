---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, Edit, Bash]
model: sonnet
runs: 3
---
Scaffold this minimal repo in the current directory: run `git init`, `git remote add origin git@github.com:acme/app.git`, and create these files exactly:

`.markdownlint.jsonc`:
```
{ "default": true, "MD013": false, "MD033": false }
```

`.github/ml-strict.jsonc`:
```
{ "default": true }
```

`.github/workflows/docs.yml`:
```
name: docs
on: [pull_request]
jobs:
  markdownlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx markdownlint-cli2 --config .github/ml-strict.jsonc "**/*.md"
```

That scaffolding is the repo as it exists. Now, as a separate task:

Markdown lint is red on every PR in CI but clean on my machine. CI errors are all `MD013/line-length` and `MD033/no-inline-html`. Locally I run `npx markdownlint-cli2 "**/*.md"`. Why the difference and what's the right fix?
