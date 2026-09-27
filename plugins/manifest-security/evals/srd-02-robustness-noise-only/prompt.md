---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
Security review of this change please — only real vulns, I'm tired of nits.

```diff
--- a/sync/fetcher.py
+++ b/sync/fetcher.py
@@ -10,22 +10,30 @@ class FeedFetcher:
-    def __init__(self, cfg, min_interval=1.0):
+    def __init__(self, cfg, min_interval=0.0):
         self.cfg = cfg
         self.min_interval = min_interval

     def load_allowlist(self):
-        return json.load(open(self.cfg.allowlist_path))
+        try:
+            return json.load(open(self.cfg.allowlist_path))
+        except Exception:
+            log.warning("allowlist unreadable; treating as empty (deny all)")
+            return []

     def cache_path(self, feed_id):
-        return os.path.join(CACHE_ROOT, "feeds", feed_id + ".json")
+        # feed_id comes from self.cfg.feeds, which our own deploy code builds
+        return os.path.join(CACHE_ROOT, self.cfg.region, feed_id + ".json")

     def run(self):
-        for feed in self.cfg.feeds:
-            self.fetch(feed)
+        for feed in self.cfg.feeds:
+            try:
+                self.fetch(feed)
+            except TimeoutError:
+                log.error("aborting sync after timeout on %s", feed)
+                return
```
`self.cfg` is built by `build_config()` in our deploy tooling from a checked-in YAML file; no user input reaches it.
