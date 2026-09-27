---
type: llm
weight: 1
---
Score 1 only if the answer identifies BOTH: (a) `build_key` using only
`bill_id:quarter` collides when two different firms report expenditures on the
same bill in the same quarter — the second HB204 row's dict assignment silently
overwrites the first, so the $12,500 expenditure from the first firm is dropped
from the aggregate entirely (only the $4,800 row survives) — and recommends
including a filer/registrant id in the key or aggregating per-filer instead of
last-write-wins; AND (b) `if rec["lobbyist_count"]:` in `summarize` treats the
surviving HB204 row's legitimate `lobbyist_count` of `0` as falsy and reports
"lobbyist count unknown" instead of stating it's 0, needing an
`is not None` check. Score 0 if it misses either bug or says the code is correct
against this sample.
