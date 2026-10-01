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
--- a/web/profile.py
+++ b/web/profile.py
@@ -40,6 +40,7 @@ def update_profile(req):
     user.display_name = req.form["display_name"][:64]
+    user.timezone = req.form.get("timezone", "UTC")
     db.commit()
```
Unchanged file (not in diff), web/render.py:
```python
def render_bio(user):
    return Markup(f"<p>{user.bio}</p>")   # line 12
```

Candidates:
- idx 0 (in_diff): Stored value `timezone` written without validation (web/profile.py:42).
- idx 1 (off_diff): Stored XSS — `user.bio` rendered with `Markup` without escaping (web/render.py:12).
