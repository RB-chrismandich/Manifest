---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
This overnight job stalled. Log tail:

```
2026-09-20 01:12:04 fetched 2314/9000 item=A-2314 0.21s
2026-09-20 01:12:04 fetched 2315/9000 item=A-2315 0.19s
2026-09-20 01:12:05 fetched 2316/9000 item=A-2316 0.22s
2026-09-20 01:12:05 fetched 2317/9000 item=A-2317 0.20s
(no further output; process still alive at 07:40)
```

The vendor status page is green and `curl https://api.example.com/v2/items/A-2318` returns 200 instantly right now. Why did it stall, and how do I get this 9,000-item run to finish reliably?
