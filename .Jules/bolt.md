# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-04-17 - Pre-compiling Regex in Loops

**Learning:** Using `re.search(r"pattern", text)` inside a loop (like iterating
through agent results in `ValidationEngine`) causes Python to re-compile the
regular expression or rely on its internal cache, adding unnecessary overhead
on every iteration.

**Action:** Always pre-compile regular expressions using `re.compile()` as
class or module-level attributes when they are evaluated inside loops,
particularly for validation strings.
