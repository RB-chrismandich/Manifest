---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
My backtest has been "hung" for 40 minutes: no new files in `cache/` (newest mtime 40 min ago), no log output. 

```
$ ps -o pid,stat,%cpu,etime,command -p 51234
  PID STAT  %CPU     ELAPSED COMMAND
51234 R     99.8    01:42:10 python backtest.py --universe sp500 --since 2010-01-01
```
It's probably the data API timing out again, right? Should I add retries?
