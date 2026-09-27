---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the answer gives runnable Python that removes the duplicated logic by importing `format_date` from `utils.dates` (e.g. `from utils.dates import format_date`) and either calls `format_date(ts)` from `format_order_date` or replaces its call sites with `format_date`. Score 0 if the import is missing (the code would raise NameError), if the fix is described only in prose with no code, or if the duplicated `strftime` logic is still present.
