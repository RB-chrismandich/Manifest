---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Findings after retiring `llm-proxy` (macOS):

```
$ ls ~/Library/LaunchAgents | grep llm-proxy
$ launchctl list | grep llm-proxy
$ pgrep -fl llm-proxy
4312 /usr/local/bin/llm-proxy --port 4000 --db ~/.llm-proxy/proxy.db
$ lsof -i :4000
llm-proxy 4312 me 7u IPv4 ... TCP localhost:4000 (LISTEN)
$ ls ~/.llm-proxy
proxy.db  proxy.log  llm-proxy.pid
```

Clean it up.
