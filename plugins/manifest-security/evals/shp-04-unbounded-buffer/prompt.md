---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Our internal aggregator proxies a partner's NDJSON export with an API key. Anything wrong with this?

```python
def export():
    req = urllib.request.Request(PARTNER_URL, headers={"Authorization": f"Bearer {KEY}"})
    body = urllib.request.urlopen(req).read()          # sometimes several GB
    rows = [json.loads(l) for l in body.splitlines()]
    return Response(json.dumps(rows), mimetype="application/json")
```
