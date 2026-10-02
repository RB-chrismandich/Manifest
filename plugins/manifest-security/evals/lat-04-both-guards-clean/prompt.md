---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Final check before merge — does this LLM-driven file writer have any path traversal issue?

```python
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
BASE = Path("/srv/agent/drafts").resolve()

def write_draft(parsed: dict) -> Path:
    name = parsed["name"]
    if not SLUG.fullmatch(name):
        raise ValueError("invalid name")
    target = (BASE / name).resolve()
    target.relative_to(BASE)          # raises ValueError on escape
    target.mkdir(exist_ok=True)
    out = target / "draft.md"
    out.write_text(parsed["body"])
    return out
```
