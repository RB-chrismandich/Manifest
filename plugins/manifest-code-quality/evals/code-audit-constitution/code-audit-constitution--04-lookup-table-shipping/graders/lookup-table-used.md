---
type: llm
focus: {source: file, path: shipping.py}
weight: 1
---
The original `shipping_cost` grew a 6-branch if/elif chain keyed on region code — past the "third real case" point where the constitution calls for a lookup table instead of another branch. Score 1 only if the final file replaces the if/elif chain with a dict/lookup table (e.g. a module-level `SHIPPING_BASE_RATES` dict) keyed by region, with a `.get(region, <default>)`-style lookup, AND every original region's base rate is preserved exactly (US 5.00, CA 7.50, MX 9.00, EU 12.00, UK 11.00, AU 15.00) AND the unknown-region default of 20.00 still applies AND the `+ weight_kg * 0.5` rounding formula is unchanged. Score 0 if an if/elif chain of comparable length remains, or if any rate/default was changed.
