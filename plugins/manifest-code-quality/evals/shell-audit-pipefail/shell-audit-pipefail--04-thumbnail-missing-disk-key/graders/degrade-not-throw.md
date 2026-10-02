---
type: llm
weight: 0.5
---
Score 1 only if the fix stops the Python one-liner from raising a `KeyError` on a host with no `"disk"` key — by using `.get()` (with a default, or followed by an explicit presence check / controlled `sys.exit`) or an explicit `"disk" in d` check — instead of direct `d["disk"]["used_pct"]` indexing. Score 0 if the one-liner still indexes the missing key directly and relies only on the shell guard to catch the traceback.
