---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
---
Write pytest unit tests for `sensor_z_score` below. I want coverage for a normal spike-detection case (a reading that's clearly anomalous against its history) and the degenerate case where the history has no variance at all.

```python
def sensor_z_score(reading, history):
    n = len(history)
    mean = sum(history) / n
    variance = sum((x - mean) ** 2 for x in history) / n
    stdev = variance ** 0.5
    if stdev == 0:
        return None
    return (reading - mean) / stdev
```
