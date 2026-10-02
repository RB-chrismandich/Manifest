---
type: llm
weight: 1
---
Score 1 only if the answer identifies that `claude -p "$(cat "$CONTEXT_FILE")"` passes the (potentially multi-megabyte) file content as a command-line argument, risking an "Argument list too long" / ARG_MAX failure on a big release, AND proposes piping the content via stdin instead (e.g. `cat "$CONTEXT_FILE" | claude -p "<short instruction>"` or `printf '%s' "$content" | claude -p ...`) while keeping only a short fixed instruction on argv. Score 0 otherwise.
