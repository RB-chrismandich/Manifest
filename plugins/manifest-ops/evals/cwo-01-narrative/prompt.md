---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
My Python backtest pulls daily bars for ~4,000 tickers from a market-data REST API, sequentially, through one long-lived requests.Session. It runs fine for the first ~800 tickers, then just hangs: no exception, CPU near 0. When I curl one of the tickers it hung on, it returns 200 in about 300ms. I already set timeout=30 and added a urllib3 Retry adapter; it still hangs. What should I do so the backtest actually completes?
