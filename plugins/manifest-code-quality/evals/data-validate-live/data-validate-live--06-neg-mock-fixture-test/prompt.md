---
max_turns: 10
timeout_seconds: 180
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Can you write a pytest unit test for this function using a couple of made-up,
clean sample amounts like "100.00" and "250.50"? No need to hit any real data —
I just want basic coverage for the happy path.

```python
def parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))
```

Just put the code in your reply — no need to create files.
