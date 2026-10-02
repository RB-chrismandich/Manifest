---
type: llm
weight: 1
---
Score 1 only if the answer flags `eval "curl ... '$1' ...$SLACK_WEBHOOK"` inside `notify()` as a command-injection risk: `eval` re-parses the interpolated `$1` (the message text), so a message containing shell metacharacters (`;`, `` ` ``, `$(...)`, quotes) would execute as commands, AND the answer proposes removing `eval` — e.g. calling `curl` directly with the JSON payload built via `printf`/a quoted variable or `--data-binary` instead of building a string for `eval`. Score 0 otherwise.
