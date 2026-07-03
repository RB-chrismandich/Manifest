---
name: config-validate-native
description: Use before deploying any app that parses its own config file (Glance, nginx, Traefik, Prometheus, Terraform, etc.) — validate with the application's OWN parser, not a generic linter, because generic linting passes configs the app rejects.
---
# Validate Config With the App's Own Parser, Not a Generic Linter

Generic YAML/JSON linting only checks syntactic well-formedness. It happily passes structurally-valid-but-semantically-broken configs (e.g. an `$include` that collapses list items into duplicate keys, an unknown widget field, an unresolved variable). The application's own validator parses the config exactly as the runtime will. Make it the authoritative pre-deploy gate.

1. **Find the app's validate/dry-run subcommand** before writing config. Examples: `glance config:validate` / `config:print`, `nginx -t`, `traefik --configFile ... (healthcheck)`, `terraform validate`, `promtool check config`, `docker compose config`. If unsure, check `--help` for `validate`, `check`, `test`, `print`, `dry-run`.
2. **Run it in the real runtime image**, with the config mounted the same way it will be at deploy (`docker run --rm -v "$PWD/config:/app/config:ro" <image> <validate-cmd>`). Pass placeholder values for every required env var so substitution doesn't false-fail.
3. **Prefer an "assembled output" subcommand when one exists** (`config:print`, `nginx -T`) to SEE the post-include, post-substitution structure. This is how you catch include/merge bugs that linting and even `validate` summaries hide.
4. **Treat exit code 0 with empty output as success only after confirming the tool prints errors when given a known-bad config** — verify the validator actually fails loudly before trusting a silent pass.
5. **Gate every commit on this**, not just the final one — run it after each config edit so a structural break is caught at the edit that introduced it, not three changes later at deploy.
6. **Static linting is still worth running** for fast feedback, but it is necessary-not-sufficient. The app's parser is the source of truth.
