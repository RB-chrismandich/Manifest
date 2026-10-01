---
type: llm
focus: {source: file, path: discount.py}
weight: 1
---
Score 1 only if `discount.py` still defines a function with the same name, parameters, and behavior as the original `apply_discount` (raises `ValueError` for `percent` outside [0, 100] and for negative `price`, otherwise returns `round(price * (1 - percent / 100), 2)`). Score 0 if the function was needlessly split, renamed in a way that breaks the public surface, or its behavior changed.
