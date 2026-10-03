---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Bolt PR #620 adds `transient=True` to the progress bar in src/ui.py. But I just merged #610 which did exactly that. `git grep -n "transient=True" origin/main -- src/ui.py` → `src/ui.py:42: with Progress(transient=True) as p:`. #620 is still green and mergeable. Merge it too?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
