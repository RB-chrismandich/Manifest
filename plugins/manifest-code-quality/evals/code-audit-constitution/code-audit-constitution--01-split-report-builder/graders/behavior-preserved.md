---
type: llm
focus: {source: file, path: report_builder.py}
weight: 1
---
Score 1 only if `build_report` in the final file still supports the same parameters (`rows`, `min_amount`, `currency`, `include_zero`) and the same overall logic as the original: rows are skipped when not a dict, missing name/amount, null amount, non-numeric amount, below `min_amount`, zero amount when `include_zero` is False, or blank name; and the output still reports total, average, largest, smallest, entry/skipped counts, unique-name count, a top-5-by-total section, and a full per-row listing. Score 0 if any of this behavior was dropped or changed while splitting the function.
