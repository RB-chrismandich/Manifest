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
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - name: Build & test
        run: |
          npm ci
          npm run build
          npm run typecheck
          npm test -- --ci
```

That scaffolding is the repo as it exists. Now, as a separate task:

The jobs API says step `Build & test` failed. Logs aren't available yet. How do I figure out which part failed?
