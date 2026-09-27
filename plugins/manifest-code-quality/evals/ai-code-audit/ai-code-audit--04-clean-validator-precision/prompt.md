---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Agent, Read, Write, Grep, Glob, "Bash(mkdir:*)", "Bash(ls:*)", "Bash(grep:*)", "Bash(python3:*)", "Bash(node:*)", "Bash(git:*)"]
runs: 3
---
First save each file below into this workspace at the path given in its header comment, then run the audit against that local tree.

Before we move this into the shared utils package, can you run an ai-code-audit pass on it?

```python
# validators.py
import re

_DIGITS = re.compile(r"[0-9]+")


def parse_positive_int(raw: object, field_name: str) -> int:
    """Parse a positive integer from untrusted input.

    Raises TypeError if `raw` is not a str (None, bool, float and int are all
    rejected rather than coerced) and ValueError naming the field and value if
    it is not an ASCII base-10 integer greater than zero.
    """
    if not isinstance(raw, str):
        raise TypeError(f"{field_name} must be a string, got {type(raw).__name__}")
    text = raw.strip()
    if not _DIGITS.fullmatch(text):
        raise ValueError(f"{field_name} must be a positive integer, got {raw!r}")
    value = int(text)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")
    return value
```
