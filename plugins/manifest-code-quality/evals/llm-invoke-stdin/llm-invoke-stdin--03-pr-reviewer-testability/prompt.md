---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
I want to unit test `review_pr_description` in CI without ever calling the real gemini CLI or hitting the network. What's the cleanest way to do that, and is there anything else wrong with this function first?

```python
import subprocess

REVIEWER_CLI = "gemini"

def review_pr_description(diff_text: str) -> str:
    return subprocess.run(
        [REVIEWER_CLI, "-p", f"Review this diff and flag risks:\n{diff_text}"],
        capture_output=True, text=True,
    ).stdout
```
