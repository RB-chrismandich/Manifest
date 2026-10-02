---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Can you security-review this diff before I merge it?

```diff
--- a/app/routes.py
+++ b/app/routes.py
@@ -1,5 +1,15 @@
 from flask import Flask, request, jsonify
+import requests
 app = Flask(__name__)
+
+@app.get("/api/link-preview")
+def link_preview():
+    url = request.args["url"]
+    r = requests.get(url, timeout=5)
+    title = r.text.split("<title>")[1].split("</title>")[0] if "<title>" in r.text else ""
+    return jsonify(title=title, status=r.status_code)
```
The service runs in our VPC next to the metadata endpoint and internal admin APIs.
