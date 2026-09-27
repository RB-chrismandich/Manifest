---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Harden this deploy workflow — it deploys to prod after CI succeeds:

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: some-org/deploy-action@v2
        with:
          token: ${{ secrets.PROD_DEPLOY_TOKEN }}
          branch: ${{ github.event.workflow_run.head_branch }}
```
