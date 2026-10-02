---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from our dotfiles deployer repo; you don't have a checkout.)

On my new laptop, `~/.cursor/` has `scripts` and `config` links but not `prompts`, `skills`, or `.plans`. The deploy log ends:

```
[deploy] linking shared assets into /Users/me/.cursor
[deploy]   scripts -> ok
[deploy]   config -> ok
[deploy]   prompts ...
curl: (28) Operation timed out after 30001 milliseconds
[bootstrap] aborted (exit 28)
```

`link_shared_assets` loops over all five and our tests for it pass on other machines. What happened and what should I do?
