---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
We gated our deploy command on author_association. Anything still wrong?

```yaml
on:
  issue_comment:
    types: [created]
jobs:
  deploy:
    if: >
      github.event.issue.pull_request &&
      contains(github.event.comment.body, '/deploy') &&
      contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: refs/pull/${{ github.event.issue.number }}/head
      - run: ./scripts/deploy.sh
        env:
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```
