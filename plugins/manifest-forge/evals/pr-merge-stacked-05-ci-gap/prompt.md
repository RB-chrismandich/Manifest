---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
runs: 3
---
Our child PRs in a 3-PR stack on GitHub never run CI. The workflow file has:

```yaml
on:
  pull_request:
    branches: [main]
```

I want to merge the whole stack into main safely. What order do I merge in, and what do I need to fix first?
