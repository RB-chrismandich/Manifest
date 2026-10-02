---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Review this proxy handler for problems:

```python
@app.get("/weather")
def weather():
    url = f"{UPSTREAM}/v1/forecast?city={request.args['city']}&api_key={os.environ['WX_KEY']}"
    log.info("GET %s", url)
    try:
        return jsonify(requests.get(url, timeout=5).json())
    except Exception as e:
        return jsonify(error=str(e), url=url), 502
```
