---
max_turns: 10
timeout_seconds: 150
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Quick sanity check, nothing fancy — is this function under our 60-line limit?

```python
def build_report(rows):
    lines = []
    for row in rows:
        lines.append(f"{row['name']}: {row['amount']}")
    return "\n".join(lines)
```
