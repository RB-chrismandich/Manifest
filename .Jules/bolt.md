## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.
## 2026-02-14 - Python Regex Optimization
**Learning:** Re-compiling regular expressions inside loops via `re.search` (even with internal caching) creates unnecessary overhead, especially when checking against multiple large agent outputs containing thousands of tokens. Pre-compiling `re.Pattern` objects as class attributes allows efficient searching without recompilation.
**Action:** Always pre-compile `re` objects as class or module-level variables when they are used within loops or frequently called functions.
