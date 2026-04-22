## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s
sleep) creates significant overhead due to process forking. Replacing `date +%s`
with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over
external commands inside loops.

## 2025-04-22 - Fast YAML parsing

**Learning:** Using `yaml.safe_load()` in PyYAML has significant overhead as it
runs in pure Python.
**Action:** Attempt to import `CSafeLoader` and use
`yaml.load(data, Loader=CSafeLoader)` instead to parse YAML config files up to
80% faster. Fall back to `SafeLoader` if `CSafeLoader` is unavailable.
