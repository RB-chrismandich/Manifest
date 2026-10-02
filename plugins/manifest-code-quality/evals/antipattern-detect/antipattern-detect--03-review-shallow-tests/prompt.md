---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Two different reviewers on this PR independently flagged the same problem: our tests for the pricing module call the function and check that it didn't throw, but never assert on the actual value returned. Here's one of the flagged tests:

```python
def test_calculate_price():
    result = calculate_price(item, quantity=2)
    assert result is not None
```

Is this worth capturing as a pattern we keep hitting?

Just give me the analysis and the knowledge-base entry you would record (category, mechanism, detection cue, prevention rule). Don't try to save it anywhere — the knowledge base isn't available in this environment.
