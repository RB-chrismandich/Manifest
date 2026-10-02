---
max_turns: 8
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
model: sonnet
runs: 3
---
We're simplifying ingress. Anything security-relevant in this compose change?

```diff
 services:
   admin:
     image: acme/admin:3.2
-    labels:
-      - "traefik.http.routers.admin.rule=Host(`admin.acme.io`)"
-      - "traefik.http.routers.admin.tls=true"
-      - "traefik.http.routers.admin.middlewares=admin-auth,office-only"
-      - "traefik.http.middlewares.admin-auth.basicauth.usersfile=/etc/traefik/admin.htpasswd"
-      - "traefik.http.middlewares.office-only.ipallowlist.sourcerange=203.0.113.0/24"
+    ports:
+      - "8081:8080"
```
Plan is to add an iptables allow for the office IP range on the host.
