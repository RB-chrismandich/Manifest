---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Implement issue #91: make slugify strip trailing hyphens. Current code: `return re.sub(r'[^a-z0-9]+', '-', s.lower())`.

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
