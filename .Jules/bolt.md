## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-11 - Python Regex & String Optimization
**Learning:** Pre-compiling regexes in Python using `re.compile` provides minimal performance gain for frequently used patterns due to internal caching in `re` module, but centralizing them improves readability. However, moving repeated string operations (like `.lower()`) out of loops is critical for scalability with large inputs.
**Action:** Always compute derived values (like lowercased strings) once outside of loops when multiple consumers need them.
