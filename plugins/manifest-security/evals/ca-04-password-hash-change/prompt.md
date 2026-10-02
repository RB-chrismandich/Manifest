---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
We're migrating password storage to be faster at login. Diff below — thoughts?

```diff
-def hash_pw(pw: str) -> str:
-    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
+def hash_pw(pw: str) -> str:
+    return hashlib.md5(pw.encode()).hexdigest()
```
