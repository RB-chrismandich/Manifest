---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
My nightly digest job started crashing today with `OSError: [Errno 7] Argument list too long`. It was working fine until we started including today's full ticket export in the digest. Here's the relevant chunk — why does this suddenly fail on big exports, and how do I fix it for good?

```python
import subprocess

def build_digest(tickets_text: str) -> str:
    prompt = f"Summarize these tickets for the daily digest:\n\n{tickets_text}"
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, check=True,
    )
    return result.stdout
```
