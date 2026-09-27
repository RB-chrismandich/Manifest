---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
This spike-detection test is failing and I can't figure out why. We feed it an obvious surge — 500 requests/min against a baseline of ~120 — and `is_spike` still comes back `False`. Is the detection logic broken?

```python
import statistics

def z_score(value, baseline):
    mean = statistics.mean(baseline)
    stdev = statistics.pstdev(baseline)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev

def is_spike(value, baseline, threshold=2.0):
    return z_score(value, baseline) > threshold

def test_spike_detected_on_surge():
    baseline = [120 for _ in range(10)]
    assert is_spike(500, baseline) is True
```
