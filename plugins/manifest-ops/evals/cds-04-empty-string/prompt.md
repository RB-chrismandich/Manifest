---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from my server; you don't have the files.)

To fix a "variable not found" error I added a passthrough to my compose service:

```yaml
environment:
  HTTP_PROXY: ${HTTP_PROXY}
```

Now on hosts where I don't use a proxy (HTTP_PROXY unset), the app refuses to start with `config: invalid value type for proxy: expected URL`. On proxy hosts it works. What should I do?
