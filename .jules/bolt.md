## 2026-01-27 - Bash YAML Parsing Bottleneck
**Learning:** The codebase relies on `parallel_agent.sh` which parses `services.yml` using multiple `sed`/`grep` passes (one per key). This is O(N*M) process spawning where N is number of keys and M is parsing overhead.
**Action:** Replaced with single-pass `awk` parsing that outputs shell variable assignments for `eval`. This reduces process spawning from ~12 to 1 for config loading. Future bash scripts in this repo should use `awk` for config parsing if `jq` or `yq` are not guaranteed.

## 2026-01-29 - Incomplete Parsing Migration
**Learning:** Previous optimization to `parallel_agent.sh` switched to `awk` for parsing but missed `minimum_agents`, leaving expensive `grep` pipelines. "Optimized" code often has leftover unoptimized patterns.
**Action:** thoroughly audit files for similar patterns when applying an optimization strategy, rather than assuming the existing implementation is consistent.

## 2026-01-30 - Bash Process Forking Overhead
**Learning:** Repeated calls to `command -v` and `seq` inside loops or frequently called functions create significant overhead due to process forking. In `parallel_agent.sh`, `json_escape` checked dependencies on every call, and retry loops spawned `seq` processes.
**Action:** Use native Bash constructs (`for ((...))`) and detect dependencies once at startup to conditionally define optimized function implementations (dynamic dispatch pattern).

## 2026-01-31 - Grep Pipeline to Awk Optimization
**Learning:** Replaced a loop spawning 4 processes per iteration (grep | tr) with a single awk process. This significantly reduces fork overhead in shell scripts, especially when processing multiple files.
**Action:** Identify sequences of `grep | cut/tr/sed` inside loops and consolidate them into single-pass `awk` scripts.
