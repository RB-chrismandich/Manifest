---
type: llm
weight: 1
---
Score 1 only if the fix splits the `local` declaration from the assignment (e.g. `local status; status="$(fetch_status "$host" | jq -r '.status')" || { ...; return 1; }`) or otherwise makes the guard observe the pipeline's real exit status (e.g. checking `${PIPESTATUS[0]}` before the value is assigned via `local`), so the guard actually fires when `fetch_status` fails. Score 0 if the fix keeps `local` and the assignment combined on one line.
