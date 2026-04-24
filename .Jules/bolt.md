# Bolt Journal

## 2026-02-07 - Bash Loop Performance
**Learning:** Calling external commands like `date` inside tight loops (e.g., 0.1s sleep) creates significant overhead due to process forking. Replacing `date +%s` with the builtin `$SECONDS` variable eliminates this overhead.
**Action:** Always prefer shell builtins (like `$SECONDS` for elapsed time) over external commands inside loops.

## 2025-04-24 - Avoid regex compilation inside high-frequency loops
**Learning:** In the `parallel_agent.py` script, the `ValidationEngine` and
`SynthesisEngine` were dynamically compiling regular expressions using
`re.search()` for multiple string patterns on every agent output validation.
This creates significant overhead when iterating over large text outputs from
multiple agents.
**Action:** Pre-compile regular expressions using `re.compile()` as class
attributes. Use `self.PATTERN.search(text)` inside loops and methods to
eliminate compilation overhead during hot-path execution.
