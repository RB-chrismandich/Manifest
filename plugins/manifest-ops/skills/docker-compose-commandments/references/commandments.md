# The Ten Commandments — rationale and remedy

Each entry: what the rule is, the failure it prevents, and the exact fix. Rule
ids are stable forever and are what bypass markers cite.

Machine-readable source: `config/compose_commandments.yml`.

---

## DC-001 — Thou Shalt Not Use `latest` · high

**Rule.** Every service pins an explicit image version, and where the registry
supports it a digest.

**Failure it prevents.** `latest` is a pointer, not a version. The image you
tested and the image that starts after the next `docker compose pull` can be
different builds with different CVEs and different behaviour, with nothing in
your git history recording that anything changed. A rollback cannot get you
back to what was running, because the tag no longer resolves there.

**Fix.** `postgres:16.2-alpine`, better `postgres:16.2-alpine@sha256:…`. The
digest is what makes the pull reproducible; the tag stays for readability.

**Delegation.** This checker only *detects* DC-001. Resolving the concrete
version and digest belongs to Manifest's version-pinning tool
(`~/.claude/scripts/version_pin.sh`), which already handles compose files
alongside `requirements.txt` and Dockerfiles. Two tools resolving pins
independently is how their semantics drift apart. That script is part of the
full Manifest install; on a standalone install of this plugin, pin by hand.

---

## DC-002 — Thou Shalt Keep Secrets Out of Version Control · high

**Rule.** Credentials arrive by `${VAR}` interpolation, `env_file`, or a Docker
`secret`. Never as a literal in the compose file.

**Failure it prevents.** A literal committed once is in the history forever;
rotating the credential does not remove it, and every clone, fork, and CI cache
has a copy. Compose files are also the file people paste into issues.

**Fix.** Interpolate and keep the value in an untracked `.env`:

```yaml
environment:
  DB_PASSWORD: ${DB_PASSWORD}
```

Better, for anything the container can read from disk, use a secret so the
value never enters the process environment (where any child process, crash
dump, or `docker inspect` can read it):

```yaml
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets: [db_password]

secrets:
  db_password:
    file: ./secrets/db_password.txt   # gitignored
```

Confirm `.env` and `secrets/` are in `.gitignore` — the checker reads the
compose file, not your ignore rules.

---

## DC-003 — Thou Shalt Define Explicit Healthchecks · medium

**Rule.** A depended-upon service declares a `healthcheck`, and its dependants
wait on `condition: service_healthy`.

**Failure it prevents.** Bare `depends_on` waits only for the container to be
*created*. Postgres takes seconds to accept connections after the process
starts, so the app races it, crashes on connect, and either restart-loops or —
worse — starts in a degraded state that looks healthy. This is the single most
common "works on my machine, flaky in CI" compose bug.

**Fix.**

```yaml
    depends_on:
      db:
        condition: service_healthy
```

with, on `db`:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
```

`start_period` matters for slow-booting services: failures during it do not
count against `retries`.

---

## DC-004 — Thou Shalt Enforce Resource Limits · high

**Rule.** Every service caps CPU and memory.

**Failure it prevents.** An unbounded container with a memory leak does not
die politely — it drives the host into swap or invokes the OOM killer, which
picks its victim by heuristics and frequently kills a *different*, innocent
container. One buggy service takes down the whole stack.

**Fix.**

```yaml
    deploy:
      resources:
        limits:
          cpus: "0.50"
          memory: 512M
```

`deploy.resources.limits` is honoured by `docker compose up` in Compose v2 as
well as by Swarm. The older `mem_limit`/`cpus` service-level keys still work
and also satisfy this rule.

---

## DC-005 — Thou Shalt Isolate Networks · high

**Rule.** Stateful and internal services sit on a dedicated network, ideally
`internal: true`, that no internet-facing container shares.

**Failure it prevents.** Every service on the implicit default network can
reach every other on every port. One RCE in the web tier is then one `psql`
away from the database. `internal: true` additionally removes the network's
route to the outside, so a compromised database container cannot exfiltrate
outbound.

**Fix — and the part most templates get wrong.** The edge service must join
*both* networks. Putting `web` on `app-net` and `db` on `db-net` and nothing
else means they cannot communicate at all:

```yaml
services:
  web:
    networks: [app-net, db-net]   # bridges public and internal
  db:
    networks: [db-net]            # internal only

networks:
  app-net:
    driver: bridge
  db-net:
    internal: true
```

The checker flags two distinct conditions: a service with no explicit
`networks:` at all, and a stateful service sharing a network with a service
that publishes a host port.

---

## DC-006 — Thou Shalt Persist State via Named Volumes · medium

**Rule.** Durable data lives in a named volume, not a host bind mount.

**Failure it prevents.** Bind mounts couple the container to the host's
filesystem layout, uid mapping, and platform semantics. The same compose file
that works on Linux corrupts a Postgres data directory on Docker Desktop for
macOS, because the osxfs/gRPC-FUSE layer does not honour the fsync and
locking guarantees the database assumes. Named volumes are managed by the
Docker engine and behave consistently.

**Fix.**

```yaml
    volumes:
      - db_data:/var/lib/postgresql/data

volumes:
  db_data:
```

Bind mounts remain correct for read-only config injection and for source code
in development — the rule targets mounts onto *stateful* paths.

---

## DC-007 — Thou Shalt Run as Non-Root · medium

**Rule.** A service sets a non-root `user:`, or documents why it cannot.

**Failure it prevents.** Root in the container is uid 0 on the host unless user
namespaces are configured, which by default they are not. Combine that with any
bind mount and a container process can write host files as root. It also means
any container escape starts from the strongest possible position.

**Fix.** `user: "1000:1000"`, matching a uid the image's files are owned by.
Where an image genuinely requires root — one that chowns a volume on first
boot, for instance — record it:

```yaml
    user: root  # compose-commandments:ignore DC-007 — chowns the data volume at init
```

Pair this with `security_opt: [no-new-privileges:true]`, which the checker does
not require but which closes the setuid escalation path.

---

## DC-008 — Thou Shalt Cap Log Output · medium

**Rule.** The `json-file` and `local` drivers are configured with `max-size`
and `max-file`.

**Failure it prevents.** Default `json-file` logging is unbounded. A service
that logs a stack trace per request fills `/var/lib/docker` until the host disk
is full, at which point every container on the box fails — usually with errors
that point anywhere but the logs.

**Fix.**

```yaml
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Services shipping to an external collector (`gelf`, `fluentd`, `awslogs`,
`syslog`) are exempt automatically — those drivers do not accumulate on disk.

---

## DC-009 — Thou Shalt Keep Configuration DRY · low

**Rule.** Configuration repeated across three or more services is factored into
a YAML anchor or an `x-` extension field.

**Failure it prevents.** Not verbosity — drift. Six copies of a logging block
means the next change updates five of them, and the sixth silently keeps the
old behaviour.

**Fix.**

```yaml
x-logging-defaults: &logging-defaults
  logging:
    driver: json-file
    options: {max-size: "10m", max-file: "3"}

services:
  web:
    <<: *logging-defaults
```

Merge several with `<<: [*service-defaults, *logging-defaults]`.

**How this is detected.** Anchors are expanded by the parser, so the parsed
document looks identical whether or not anchors were used — an anchored file
and a copy-pasted one are indistinguishable in the tree. The rule therefore
reads the raw text for `x-` keys and `<<: *` merges, and stays silent when it
finds them.

---

## DC-010 — Thou Shalt Configure Graceful Shutdowns · medium

**Rule.** Stateful services declare a `stop_grace_period` long enough to flush
and close cleanly.

**Failure it prevents.** `docker compose down` sends SIGTERM, waits 10 seconds
by default, then SIGKILLs. A database mid-checkpoint, or a queue worker holding
unacknowledged messages, does not finish in 10 seconds — so it dies hard, and
the next start pays for it with crash recovery or, for engines without a
journal, data loss.

**Fix.** `stop_grace_period: 30s`. Confirm the process actually handles SIGTERM:
a shell-form `CMD` in the image makes the shell PID 1, which does not forward
signals, so the grace period expires with the real process never notified.
