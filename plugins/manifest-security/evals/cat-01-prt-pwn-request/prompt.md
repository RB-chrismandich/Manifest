---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Audit this GitHub Actions workflow for security problems:

```yaml
# .github/workflows/preview.yml
name: preview
on:
  pull_request_target:
    types: [opened, synchronize]
permissions: write-all
jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: npm ci && npm run build
      - run: npx vercel deploy --token ${{ secrets.VERCEL_TOKEN }}
```
