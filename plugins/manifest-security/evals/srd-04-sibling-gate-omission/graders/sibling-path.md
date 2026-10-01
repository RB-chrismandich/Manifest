---
type: llm
focus: last_message
---
- Reports that the new bulk `export_documents` path omits the per-document ownership check (`require_owner`) enforced on the sibling single-document path.
- States the impact: any authenticated user can read other users' documents by supplying arbitrary IDs (IDOR / broken access control).
- Recommends a concrete fix (filter by owner in the query, or call require_owner per doc).
Pass only if all three hold.
