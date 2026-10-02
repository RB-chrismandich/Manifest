---
type: llm
weight: 1
---
Score 1 only if the answer flags `find "$LOG_DIR" -name $pattern` as passing `$pattern` unquoted to `-name`, subject to word-splitting/glob expansion if the pattern ever contains spaces or shell metacharacters, AND recommends quoting it (`-name "$pattern"`). Score 0 otherwise.
