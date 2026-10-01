---
type: llm
focus: {source: file, path: test_fetch_status.sh}
weight: 2
---
Pass only if ALL hold:
1. Runs the script with `HOME` set to a temp dir (mktemp -d) holding a fixture `.statusrc` for the happy path, and with no `.statusrc` for the missing-token case.
2. Replaces `curl` with a fixture stub placed first on `PATH` (so no real network call can happen), and the stub or assertions check that the token was sent.
3. Asserts the missing-token case fails non-zero (not a false green).
4. Cleans up temp dirs (trap or explicit rm).
