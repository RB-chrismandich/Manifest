---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Adversarially verify these candidate findings before I report them. Return which survive and which are refuted, with evidence.

Diff:
```diff
--- a/worker/webhook.py
+++ b/worker/webhook.py
@@ -1,4 +1,10 @@
+import os, requests
+HOOK = os.environ["TENANT_WEBHOOK_URL"]   # set per tenant from the tenant settings page
+def notify(event):
+    r = requests.post(HOOK, json=event, timeout=3)
+    return r.status_code
```
The worker runs in the shared cluster; tenant admins set TENANT_WEBHOOK_URL through the web settings page, and the platform injects it as an env var.

Candidates:
- idx 0 (in_diff): SSRF — tenant-controlled webhook URL is requested server-side from the shared cluster (worker/webhook.py:4).
