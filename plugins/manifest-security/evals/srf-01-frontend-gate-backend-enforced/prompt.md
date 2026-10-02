---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Run security-refute-findings on this candidate list.

Diff:
```diff
--- a/web/src/AdminButton.tsx
+++ b/web/src/AdminButton.tsx
@@ -3,5 +3,5 @@ export function AdminButton({ user }) {
-  if (!user.roles.includes("admin")) return null;
+  if (!user.roles.includes("admin") && !user.roles.includes("support")) return null;
   return <button onClick={() => api.post("/admin/reindex")}>Reindex</button>;
```
Backend (unchanged), api/admin.py:
```python
@router.post("/admin/reindex")
def reindex(user=Depends(require_role("admin"))):   # line 9
    ...
```

Candidates:
- idx 0 (in_diff): Privilege escalation — support users now see the admin Reindex button (web/src/AdminButton.tsx:4).
