# Bolt Journal

## 2026-02-07 - Bash Loop Performance

**Learning:** Calling external commands like `date` inside tight loops (e.g.,
0.1s sleep) creates significant overhead due to process forking. Replacing
`date +%s` with the builtin `$SECONDS` variable eliminates this overhead.

**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time)
over external commands inside loops.

## 2024-05-18 - re.compile optimization in ValidationEngine

**Learning:** Re-compiling regular expressions inside nested loops (e.g.,
`for agent_name, result in agent_results.items():` nested with
`for pattern in patterns:`) in Python using `re.search` can lead to measurable
performance overhead. Pre-compiling `re.Pattern` objects as class attributes
using `re.compile(r'pattern')` avoids cache lookup and compilation overhead when
evaluating large outputs.

**Action:** Identify and optimize inner-loop `re.search` calls by pre-compiling
regular expressions as class-level constants when parsing text outputs,
particularly for repeated validations like security checks.
