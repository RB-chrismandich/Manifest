---
type: llm
weight: 1
---
Score 1 only if the answer states that `ssh` inside the `while read` loop reads/consumes the loop's stdin so only the first host is processed, AND proposes redirecting ssh stdin (`</dev/null`, `ssh -n`) or reading on a separate file descriptor. Score 0 otherwise.
