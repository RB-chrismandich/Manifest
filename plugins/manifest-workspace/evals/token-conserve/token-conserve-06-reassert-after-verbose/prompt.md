---
max_turns: 6
timeout_seconds: 120
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Earlier in this session you answered "what does `git stash` do?" like this:

> Great question! `git stash` is a really useful command that lets you temporarily save your uncommitted changes so that you can work on something else, and then come back and re-apply them later. Essentially, it takes the modifications in your working directory and your index, and stores them away on a stack. This is super handy when you need to switch branches quickly but you're not ready to commit yet! There are also lots of options, like `git stash pop`, `git stash apply`, `git stash list`, and `git stash drop`, each of which does something slightly different. Let me know if you'd like me to go through each of them in detail!

That's the verbosity I keep getting. Re-assert token-conserve mode now, then answer: what's the difference between `git stash pop` and `git stash apply`?
