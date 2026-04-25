## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2026-02-14 - Pre-compiling Regular Expressions
**Learning:** Inline regular expression compilation in tight loops or
frequently called methods creates unnecessary overhead.
**Action:** Pre-compile regular expressions using `re.compile()` as
class attributes (e.g., in `ValidationEngine` or `SynthesisEngine`)
instead of passing raw string patterns to `re.search()` to reduce
compilation overhead.
