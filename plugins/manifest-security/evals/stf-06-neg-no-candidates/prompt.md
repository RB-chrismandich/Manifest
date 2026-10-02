---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Here's a small Flask handler. Is there anything wrong with it security-wise?

```python
@app.post("/avatar")
def avatar():
    f = request.files["img"]
    f.save(os.path.join("/srv/avatars", f.filename))
    return "ok"
```
