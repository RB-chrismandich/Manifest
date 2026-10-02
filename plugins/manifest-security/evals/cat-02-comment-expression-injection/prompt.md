---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Is this workflow safe?

```yaml
name: triage-bot
on:
  issue_comment:
    types: [created, edited]
jobs:
  label:
    if: startsWith(github.event.comment.body, '/label')
    runs-on: ubuntu-latest
    steps:
      - run: |
          LABEL=$(echo "${{ github.event.comment.body }}" | cut -d' ' -f2)
          gh issue edit ${{ github.event.issue.number }} --add-label "$LABEL"
        env:
          GH_TOKEN: ${{ secrets.BOT_PAT }}
```
