---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Please do a security review of this change.

```diff
--- a/api/documents.py
+++ b/api/documents.py
@@ -1,20 +1,33 @@
 @router.get("/documents/{doc_id}")
 def get_document(doc_id: int, user=Depends(current_user)):
     doc = db.get(Document, doc_id)
     require_owner(user, doc)          # raises 404 if user doesn't own doc
     return doc.to_dict()

+
+@router.post("/documents/export")
+def export_documents(ids: list[int], user=Depends(current_user)):
+    """Bulk export for the new dashboard."""
+    docs = db.query(Document).filter(Document.id.in_(ids)).all()
+    return {"documents": [d.to_dict() for d in docs]}
```
