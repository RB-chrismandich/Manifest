---
type: llm
focus: last_message
weight: 1
---
Pass if the answer treats `ECONNREFUSED` to the CI Postgres service as an environment/dependency failure, not an app-code bug — i.e. it says the DB service was unreachable, not ready, or misconfigured, and recommends checking the job's service/connection config (host, port, healthcheck) and the runner rather than more code fixes. It may note the config could have been broken by this PR; it must not definitively pin the cause on shared infrastructure without checking.
