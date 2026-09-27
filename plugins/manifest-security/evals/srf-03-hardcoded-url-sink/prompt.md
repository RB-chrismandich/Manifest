---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Please refute (or confirm) these candidates using the security-refute-findings procedure.

Diff:
```diff
--- a/jobs/fx.py
+++ b/jobs/fx.py
@@ -1,3 +1,7 @@
+import requests
+RATES_URL = "https://api.exchangerate.host/latest"
+def refresh(base):
+    return requests.get(RATES_URL, params={"base": base[:3]}, timeout=5).json()
```
`base` comes from a request parameter.

Candidates:
- idx 0 (in_diff): SSRF — outbound request built from user input (jobs/fx.py:4).
