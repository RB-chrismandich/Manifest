---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
We added validation after a review comment. Is this enough now?

```python
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
BASE = Path("/srv/agent/notes")

def save_note(model_output: dict):
    name = model_output["slug"]
    if not SLUG.match(name):
        raise ValueError("bad slug")
    (BASE / name).mkdir(exist_ok=True)
    (BASE / name / "note.md").write_text(model_output["text"])
```
