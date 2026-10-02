---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Fetch job stopped writing to `cache/` 25 minutes ago.

```
$ ps -o pid,stat,%cpu,etime,command -p 7781
 PID STAT %CPU  ELAPSED COMMAND
7781 S     0.0 02:10:44 python fetch_all.py
$ lsof -nP -p 7781 | grep ESTABLISHED
python 7781 me 9u IPv4 ... TCP 10.0.0.5:53122->151.101.1.10:443 (ESTABLISHED)
$ curl --max-time 10 -s -o /dev/null -w '%{http_code} %{time_total}\n' https://api.vendor.com/v1/items/48213
200 0.21
```
It uses one `httpx.Client(timeout=30)` for all ~20k requests. What's going on?
