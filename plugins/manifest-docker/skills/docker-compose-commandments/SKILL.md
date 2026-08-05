---
name: docker-compose-commandments
description: Audit or harden a docker-compose.yaml against DC-001..DC-010 — pinning, secrets, healthchecks, limits, network isolation, volumes, non-root, logs. Use for "review my compose file" or a DC-NNN finding.
---

# The Ten Commandments of docker-compose

A compose file is a deployment contract. These ten rules are the ones whose
absence shows up as a 3am incident: an image that silently changed, a password
in git history, a container that ate the host's memory, a database on the same
network as the public web tier.

The checker is `scripts/compose_check.py`; the rules are data in
`config/compose_commandments.yml`. A PostToolUse hook runs it automatically on
every compose file you edit and prints findings to stderr — it never blocks.

## The commandments

| ID | Commandment | Catches |
|----|-------------|---------|
| DC-001 | Thou Shalt Not Use `latest` | mutable or absent image tag |
| DC-002 | Thou Shalt Keep Secrets Out of Version Control | credential literal in `environment:` |
| DC-003 | Thou Shalt Define Explicit Healthchecks | missing `healthcheck`, `depends_on` that waits for start not health |
| DC-004 | Thou Shalt Enforce Resource Limits | no CPU or memory ceiling |
| DC-005 | Thou Shalt Isolate Networks | stateful service reachable from the public tier; implicit default bridge |
| DC-006 | Thou Shalt Persist State via Named Volumes | host bind mount holding durable data |
| DC-007 | Thou Shalt Run as Non-Root | no `user:`, or `user: root` |
| DC-008 | Thou Shalt Cap Log Output | unbounded `json-file` logging |
| DC-009 | Thou Shalt Keep Configuration DRY | identical block repeated across 3+ services with no anchor |
| DC-010 | Thou Shalt Configure Graceful Shutdowns | stateful service with no `stop_grace_period` |

Rationale, failure mode, and the exact remedy for each: `references/commandments.md`.

## Task

1. **Run the checker.** It is advisory (exit 0) unless `--strict`.

   ```bash
   # One file
   python3 scripts/compose_check.py docker-compose.yaml

   # Every compose file in a tree
   python3 scripts/compose_check.py .

   # One rule only, or machine-readable output
   python3 scripts/compose_check.py . --rule DC-002 --rule DC-005
   python3 scripts/compose_check.py . --json

   # CI gate: non-zero when anything is found
   python3 scripts/compose_check.py . --strict
   ```

2. **Read each finding as `file:line  DC-NNN severity [service] message`.** The
   commandment and its remedy print once per rule. Fix `high` first: DC-001,
   DC-002, DC-004 and DC-005 are the ones with a blast radius beyond the container.

3. **Apply the fix.** Edit the compose file directly. For DC-001 the checker
   deliberately only *detects* — Manifest's version-pinning tool already owns
   resolving the concrete version and digest for compose files, and two
   resolvers would drift apart:

   ```bash
   ~/.claude/scripts/version_pin.sh docker-compose.yaml
   ```

   That script ships with the full Manifest install. On a standalone install of
   this plugin it will not exist; pin the tag and digest by hand instead.

4. **Bypass only what is genuinely correct**, with a reason in the comment:

   ```yaml
   services:
     migrate:
       image: myapp:1.2.0
       user: root  # compose-commandments:ignore DC-007 — needs to chown the volume
   ```

   A bare `# compose-commandments:ignore` suppresses every rule on that line;
   naming ids suppresses only those. For a service-scoped finding with no
   offending line (a *missing* key), the marker works anywhere inside the
   service block. `# compose-commandments:ignore-file` anywhere in the file
   exempts the whole file — use it for fixtures and teaching examples, not to
   silence real findings.

5. **Re-run to confirm.** Report the before/after finding count, not "fixed".

## When authoring a new compose file

Start from `references/compose-template.yaml`, which is checker-clean and
carries a `# DC-NNN` comment on each line that exists to satisfy a commandment.

Two things that template gets right and most published examples get wrong:

- **The edge service joins both networks.** A backing service on an
  `internal: true` network and a web service on only the public network cannot
  talk to each other at all. The web tier must be on *both*; only the database
  is restricted to the internal one.
- **`version:` is omitted.** It has been obsolete since Compose v2 and current
  `docker compose` warns about it.

## Scope

Compose files only — `docker-compose.y*ml`, `compose.y*ml`, and their
`docker-compose.<env>.y*ml` overrides. Dockerfile rules are out of scope.

Two neighbouring concerns are deliberately owned elsewhere in Manifest:
supply-chain pinning across `requirements.txt`, Dockerfiles and compose alike
(`~/.claude/scripts/version_pin.sh`), and host firewall rules for a published
port (the `manifest-security` bundle's firewall audit).
