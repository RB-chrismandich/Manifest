# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2026-02-07 - Python Loop Performance

**Learning:** Calling `re.search` with inline strings inside tight loops forces
Python to recompile the regular expression on every iteration, causing
significant overhead.
**Action:** Always pre-compile regular expressions using `re.compile` as class
or module-level attributes when evaluating patterns repeatedly inside loops.
