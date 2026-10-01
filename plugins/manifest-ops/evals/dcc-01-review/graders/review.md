---
type: llm
focus: last_message
weight: 1
---
Grade the final answer. PASS only if ALL of these claims hold:
1. It flags `postgres:latest` as a mutable/unpinned image tag.
2. It flags the plaintext password (`hunter2`) in POSTGRES_PASSWORD and DATABASE_URL as a secret committed in the compose file, recommending env interpolation / an env file outside VCS / Docker secrets.
3. It flags that the database shares the default network with the publicly exposed web service (no network isolation).
4. It flags the missing healthcheck and that `depends_on` waits for container start, not DB readiness.
5. It orders findings with the high-blast-radius items (secret, latest tag, network exposure, resource limits) ahead of lower-severity ones.
