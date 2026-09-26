---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
We migrated the `skillclaw` tool runtime to a new bootstrap that's supposed to create `~/.skillclaw/{sessions,skills}` with 700 perms (it stores captured session transcripts). After migrating my Mac:

```
$ stat -f '%Sp %N' ~/.skillclaw ~/.skillclaw/*
drwxr-xr-x /Users/me/.skillclaw
drwxr-xr-x /Users/me/.skillclaw/skills
-rw-r--r-- /Users/me/.skillclaw/skillclaw.pid
$ pgrep -fl skillclaw
8120 skillclaw serve --legacy
```
What still needs doing?
