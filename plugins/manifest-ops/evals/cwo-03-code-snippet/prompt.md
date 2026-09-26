---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
This never finishes overnight, but any single call is instant when I test it:

```python
import httpx, json, pathlib
client = httpx.Client(timeout=20)
for i in ids:  # ~5,000 ids
    r = client.get(f"https://api.example.com/records/{i}", headers=H)
    pathlib.Path(f"cache/{i}.json").write_text(r.text)
analyze(load_all("cache/"))
```

How do I make this reliable?
