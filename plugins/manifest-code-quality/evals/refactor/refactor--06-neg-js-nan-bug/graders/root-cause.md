---
type: llm
weight: 1
---
Score 1 only if the answer explains that `parseInt("$19.99", 10)` returns `NaN` because the leading `$` character is not a valid digit and `parseInt` cannot begin parsing a number from a non-digit character, AND proposes a fix such as stripping non-numeric characters before parsing (e.g. `input.replace(/[^0-9.]/g, "")`) or otherwise sanitizing the currency string before calling `parseInt`/`parseFloat`. Score 0 otherwise.
