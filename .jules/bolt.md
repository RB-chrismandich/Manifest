## 2026-01-27 - Bash YAML Parsing Bottleneck
**Learning:** The codebase relies on `parallel_agent.sh` which parses `services.yml` using multiple `sed`/`grep` passes (one per key). This is O(N*M) process spawning where N is number of keys and M is parsing overhead.
**Action:** Replaced with single-pass `awk` parsing that outputs shell variable assignments for `eval`. This reduces process spawning from ~12 to 1 for config loading. Future bash scripts in this repo should use `awk` for config parsing if `jq` or `yq` are not guaranteed.
