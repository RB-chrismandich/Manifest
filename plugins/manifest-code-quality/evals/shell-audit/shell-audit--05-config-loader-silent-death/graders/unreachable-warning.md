---
type: llm
weight: 0.5
---
Score 1 if the answer notes that the "candidates were rejected" warning is unreachable when `targets` is empty (the `exit 0` fires first), so rejections are silently hidden in exactly the empty case. Score 0 if not mentioned.
