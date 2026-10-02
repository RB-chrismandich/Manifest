---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
Running `pytest` locally fails with:

```
ImportError while importing test module 'tests/test_orders.py'.
E   ModuleNotFoundError: No module named 'orders'
```

The package is in `src/orders/`. How do I fix this?
