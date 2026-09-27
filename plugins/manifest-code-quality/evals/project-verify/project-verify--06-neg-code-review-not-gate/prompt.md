---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Is the logic in this function correct? If not, what's wrong with it?

```python
def is_palindrome(s):
    return s[::-1] == s[1:]
```
