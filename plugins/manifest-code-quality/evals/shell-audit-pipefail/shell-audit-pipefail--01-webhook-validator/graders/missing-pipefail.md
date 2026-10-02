---
type: llm
weight: 1
---
Score 1 only if the answer notes that the script uses `set -eu` WITHOUT `pipefail`, and explains that when `$payload` is not valid JSON, `jq -r '.status'` fails and prints nothing, but the trailing `sed` still runs on empty input and succeeds, so the pipeline/`$()` substitution reports success and `status` silently becomes an empty string instead of "unknown" or an error — meaning a malformed payload falls through the `"$status" == "unknown"` check and gets processed as if valid. Score 0 if it doesn't identify the missing `pipefail` as part of the mechanism, or claims the malformed case is already correctly rejected.
