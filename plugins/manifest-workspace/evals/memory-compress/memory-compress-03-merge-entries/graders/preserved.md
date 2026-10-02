---
type: llm
weight: 2
---
Pass only if ALL hold:
1. The five feat/search-index entries are merged into ONE time-blocked entry (08:48-09:22 | feat/search-index).
2. The 13:40 fix/billing-rounding entry stays a SEPARATE entry (different branch, hours apart), after the merged one (chronological order).
3. All required facts survive: reindex_worker.py, SKIP_RECENT_SECS in config/search.yml changed 60→0, 22 tests passed, MR !88, commit 7f3e9a1; billing/totals.py, half-even→half-up, issue #301, 64 tests.
4. No preamble or commentary; no facts not in the source.
