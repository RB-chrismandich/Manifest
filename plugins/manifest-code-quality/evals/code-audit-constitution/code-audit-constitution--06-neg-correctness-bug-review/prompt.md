---
max_turns: 10
timeout_seconds: 200
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Can you review this palindrome check — it crashes with an IndexError on input like "level". What's wrong?

```python
def is_palindrome(s):
    s = s.lower()
    for i in range(len(s) // 2):
        if s[i] != s[len(s) - i]:
            return False
    return True
```
