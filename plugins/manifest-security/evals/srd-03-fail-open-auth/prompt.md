---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Review this PR diff for security issues:

```diff
--- a/auth/middleware.py
+++ b/auth/middleware.py
@@ -18,12 +18,15 @@ def require_scope(scope):
     def deco(fn):
         @wraps(fn)
         def inner(*a, **kw):
-            claims = verify_token(request.headers.get("Authorization", ""))
-            if scope not in claims.get("scopes", []):
-                abort(403)
+            try:
+                claims = verify_token(request.headers.get("Authorization", ""))
+                if scope not in claims.get("scopes", []):
+                    abort(403)
+            except Exception:
+                log.exception("token verification error; continuing")
             return fn(*a, **kw)
         return inner
     return deco
```
