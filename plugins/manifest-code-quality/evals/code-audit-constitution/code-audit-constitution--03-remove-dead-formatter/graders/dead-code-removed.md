---
type: llm
focus: {source: file, path: pricing/format.py}
weight: 1
---
`format_price_v1` has no caller anywhere in the given code (only `format_price_v2` is imported/used, by pricing/invoice.py). Score 1 only if the final `pricing/format.py` no longer defines `format_price_v1` at all, while `format_price_v2` is still present and unchanged (same signature, same currency-symbol behavior including the `EUR`/`GBP`/fallback cases). Score 0 if `format_price_v1` is still present (even if marked deprecated/unused via a comment), or if `format_price_v2`'s behavior was altered.
