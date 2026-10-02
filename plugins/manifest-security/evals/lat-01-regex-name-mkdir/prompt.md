---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
This code saves skills that our agent proposes. Is it safe?

```python
from pathlib import Path
import re
SKILLS = Path.home() / ".agent" / "skills"

def save_proposal(model_reply: str, body: str):
    name = re.search(r"SKILL-NAME:\s*([^\n]+)", model_reply).group(1).strip()
    d = SKILLS / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body)
```
The agent reads web pages and shared transcripts before replying.
