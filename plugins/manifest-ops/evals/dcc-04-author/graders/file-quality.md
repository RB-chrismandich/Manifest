---
type: llm
focus: {source: file, path: docker-compose.yaml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. All images are pinned to explicit versions (no `latest`, no untagged images).
2. No credential literals: passwords/secret keys come from `${VAR}` interpolation, env_file, or secrets.
3. Postgres and Redis have healthchecks, and the web service's depends_on uses `condition: service_healthy`.
4. Postgres/Redis are on an `internal: true` network while the web service is on both the public network and the internal one.
5. Resource limits are set, the web service runs as a non-root user, logging is capped (max-size/max-file or non-json-file driver), and Postgres has a `stop_grace_period`.
