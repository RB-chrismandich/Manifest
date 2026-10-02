---
type: llm
focus: {source: file, path: pricing.py}
weight: 1
---
Score 1 only if `pricing.py` no longer contains the 20-entry `TAX_RATES` dict literal inline, and instead `price_with_tax` obtains the rates through a call to a loader function (e.g. `load_tax_rates()`), with the lookup logic (`.get(state.upper(), 0.0)`) and 2-decimal rounding behavior unchanged. Score 0 if the literal dict is still embedded in this file, or if the loader is never actually called (e.g. the dict was just renamed but left inline).
