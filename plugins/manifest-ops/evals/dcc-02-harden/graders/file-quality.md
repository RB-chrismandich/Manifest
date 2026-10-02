---
type: llm
focus: {source: file, path: docker-compose.yaml}
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. The `db` service is only on an internal network (e.g. `internal: true`) and the `web` service joins BOTH the public/edge network and that internal network, so web can still reach db.
2. `db` has a healthcheck (e.g. pg_isready) and web's depends_on uses `condition: service_healthy`.
3. Memory (and ideally CPU) limits are set on the services.
4. Postgres data uses a named volume instead of the `./pgdata` bind mount.
5. The password comes from interpolation/env file/secrets, not a literal; and there is no top-level `version:` key.
