---
name: config-debug-substitution
description: Use when a containerized app reads a mounted config containing ${VAR} references and fails at runtime even though compose/k8s validated and started it — crash-loop, "variable not found", an empty/nil/invalid value, rejected credentials, or just one section, widget, or integration broken while the rest works — or when passing an unset var through injects an empty string the app rejects. The app does its OWN ${VAR} substitution, separate from orchestrator interpolation. Not for Compose's own "variable is not set" warning.
---
# Debug Two-Layer Variable Substitution (Orchestrator vs. App)

Many apps (Glance, Traefik, custom servers) perform their own `${VAR}` interpolation when reading a mounted config file.
That is a SECOND substitution layer, independent of Docker Compose / Kubernetes interpolation. A variable used in the
config but absent from the app's *own container environment* fails at app runtime — after the orchestrator has already
validated and started the container. Unset vars may arrive as empty strings, failing one widget/section at runtime
rather than crashing startup, which makes them easy to miss.

**Lead the answer with this mechanism**, even when you cannot see the user's files: say the app substitutes `${VAR}`
itself from its own container environment, and that `.env` or a clean orchestrator validation does not mean the app
process sees the variable. Then give the procedure below.

1. **Recognize the signature:** orchestrator (`docker compose config`) passes, container starts, then the app itself
   logs `environment variable X not found`, `invalid value <nil>`, or a single section silently fails while the rest
   works.
2. **Enumerate every variable the config references**, not just the obvious secrets:
   `grep -rhoE '\$\{[A-Z_]+\}' <config-dir>/ | sort -u`
3. **Enumerate every variable actually passed into the app's container** (its compose `environment:`/`env`/`envFrom`),
   and diff the two sets. Any var in the config set but not the env set is your bug.
4. **Add the missing var to the app's environment** as a passthrough (`DOMAIN: ${DOMAIN}`), not just to the
   orchestrator's `.env`. The orchestrator having a value does NOT mean the app's process sees it.
5. **For optional vars, beware empty-string injection:** passing `FOO: ${FOO}` when `FOO` is unset sends `""` to the
   app, which some parsers reject (`invalid value type`). If the app can't tolerate empty, omit the key entirely rather
   than passing a blank, and let the config use a literal/default. Never invent dummy URLs or placeholder endpoints;
   only use a documented, real endpoint the app is expected to accept.
6. **Re-validate with the app's own parser** (see `config-validate-native`) using placeholders for every enumerated var,
   so the next failure surfaces at validate time instead of mid-deploy.
