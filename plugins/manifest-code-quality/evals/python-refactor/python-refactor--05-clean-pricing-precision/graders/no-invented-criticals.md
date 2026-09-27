---
type: llm
weight: 1
---
This module uses `Decimal` arithmetic (no float-rounding issues), has type hints, a docstring, input validation on `discount_pct`, a `Final` typed constant (not a magic number), and contains no secrets, no injection, no eval/exec/pickle. Score 1 only if the answer does NOT invent a Critical or High severity finding (e.g. does not claim there is a security vulnerability, injection risk, hardcoded secret, or unsafe deserialization in this snippet). Minor/Low advisories (e.g. "add unit tests", "add a module docstring", "no upper bound sanity check on subtotal") are fine. Score 0 if any Critical/High finding is fabricated.
