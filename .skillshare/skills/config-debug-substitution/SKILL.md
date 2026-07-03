---
name: config-debug-substitution
description: Use when a containerized app crash-loops or errors on "variable not found"/empty-value despite the orchestrator validating fine — the app does its OWN ${VAR} substitution on mounted config, separate from compose/k8s interpolation.
---
# Debug Two-Layer Variable Substitution (Orchestrator vs. App)

Many apps (Glance, Traefik, custom servers) perform their own `${VAR}` interpolation when reading a mounted config file. That is a SECOND substitution layer, independent of Docker Compose / Kubernetes interpolation. A variable used in the config but absent from the app's *own container environment* fails at app runtime — after the orchestrator has already validated and started the container. Unset vars may arrive as empty strings, failing one widget/section at runtime rather than crashing startup, which makes them easy to miss.

1. **Recognize the signature:** orchestrator (`docker compose config`) passes, container starts, then the app itself logs `environment variable X not found`, `invalid value <nil>`, or a single section silently fails while the rest works.
2. **Enumerate every variable the config references**, not just the obvious secrets:
   `grep -rhoE '\$\{[A-Z_]+\}' <config-dir>/ | sort -u`
3. **Enumerate every variable actually passed into the app's container** (its compose `environment:`/`env`/`envFrom`), and diff the two sets. Any var in the config set but not the env set is your bug.
4. **Add the missing var to the app's environment** as a passthrough (`DOMAIN: ${DOMAIN}`), not just to the orchestrator's `.env`. The orchestrator having a value does NOT mean the app's process sees it.
5. **For optional vars, beware empty-string injection:** passing `FOO: ${FOO}` when `FOO` is unset sends `""` to the app, which some parsers reject (`invalid value type`). If the app can't tolerate empty, omit the key entirely rather than passing a blank, and let the config use a literal/default.
6. **Re-validate with the app's own parser** (see `app-native-config-validation`) using placeholders for every enumerated var, so the next failure surfaces at validate time instead of mid-deploy.
