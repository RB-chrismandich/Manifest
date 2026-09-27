---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Mind taking a look at this before I merge it? It's the new signature verifier for incoming webhook payloads.

```python
# webhooks/verify.py
import pickle
import hmac

def verify_and_load(payload_bytes, signature, secret):
    expected = hmac.new(secret, payload_bytes, "sha256").hexdigest()
    if signature == expected:
        return pickle.loads(payload_bytes)
    return None
```
