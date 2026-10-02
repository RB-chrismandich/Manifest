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
--- a/tools/exportcli.py
+++ b/tools/exportcli.py
@@ -1,6 +1,12 @@
+import argparse, sqlite3
+def main():
+    p = argparse.ArgumentParser(); p.add_argument("--out"); p.add_argument("--db")
+    a = p.parse_args()
+    rows = sqlite3.connect(a.db).execute("select * from notes").fetchall()
+    open(a.out, "w").write(repr(rows))
--- a/web/search.py
+++ b/web/search.py
@@ -4,3 +4,6 @@
+@app.get("/search")
+def search():
+    q = request.args.get("q", "")
+    return db.execute(f"SELECT * FROM posts WHERE title LIKE '%{q}%'").fetchall()
```
`exportcli.py` is a local developer CLI run by the user on their own machine.

Candidates:
- idx 0 (in_diff): Path traversal — `--out` lets the caller write to arbitrary paths (tools/exportcli.py:6).
- idx 1 (in_diff): SQL injection — `q` interpolated into SQL (web/search.py:7).
