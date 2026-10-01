---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Compress these memory-log entries. They're already committed in our repo's `memory/log.md`, so rewriting them is fine. Output only the compressed log.

## 08:48 | feat/search-index
Started looking at why search results are stale. Found that the indexer job `reindex_worker.py` skips documents updated in the last 60 seconds.
## 08:55 | feat/search-index
Confirmed the 60s skip window is from `SKIP_RECENT_SECS` in `config/search.yml`. Changed it to 0.
## 09:03 | feat/search-index
Ran the indexer tests, `pytest tests/search` — 22 passed.
## 09:14 | feat/search-index
Opened MR !88 for the search index fix.
## 09:22 | feat/search-index
Addressed review on MR !88: added a comment explaining why the window is 0. Pushed 7f3e9a1.
## 13:40 | fix/billing-rounding
Fixed invoice total rounding in `billing/totals.py` (round half-even → half-up); issue #301; tests 64 passed.
