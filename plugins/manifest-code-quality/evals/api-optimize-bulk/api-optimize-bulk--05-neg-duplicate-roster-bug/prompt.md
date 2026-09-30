---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
This prints our on-call roster but the last engineer shows up twice at the bottom of the list — what's wrong?

```python
engineers = ["ana", "ben", "cy", "dee"]

def fetch_profile(name):
    return {"name": name, "role": "on-call"}

roster = []
for i in range(len(engineers)):
    roster.append(fetch_profile(engineers[i]))
    if i == len(engineers) - 1:
        roster.append(fetch_profile(engineers[i]))

for person in roster:
    print(person["name"], person["role"])
```
