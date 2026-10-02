---
type: llm
weight: 1
---
Score 1 only if the answer flags `eval "grep $filter /var/log/app.log"` as a command-injection vulnerability: `filter` comes directly from a caller-supplied argument, and `eval` re-parses the resulting string, so shell metacharacters in `filter` (e.g. `;`, `|`, `$(...)`, backticks) execute as arbitrary commands, AND proposes removing `eval` entirely (e.g. `grep -- "$filter" /var/log/app.log` or validating/escaping the filter). Score 0 otherwise.
