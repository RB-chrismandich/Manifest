---
type: llm
weight: 1
---
This script already pipes the prompt via stdin (`printf '%s' "$1" | "$REVIEW_CLI" -p ...`) and already puts the CLI behind an injectable seam (`REVIEW_CLI="${REVIEW_CLI:-claude}"`). Score 1 only if the answer does NOT report a critical ARG_MAX/argv-size bug and does NOT claim the CLI is hardcoded or non-injectable/non-testable. Minor suggestions (e.g. checking the reviewer's exit status, quoting, adding an actual offline stub test) are fine. Score 0 if it invents a critical stdin/ARG_MAX or non-injectable-seam defect in this already-correct script.
