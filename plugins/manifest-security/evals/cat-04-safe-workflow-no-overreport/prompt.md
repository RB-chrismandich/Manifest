---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Security-audit this CI workflow; I want to know if it has any real attacker path.

```yaml
name: test
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1
      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c # v5.0.0
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt && pytest -q
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
```
No secrets are configured for fork PRs in repo settings.
