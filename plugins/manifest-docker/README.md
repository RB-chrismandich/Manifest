# manifest-docker

The Ten Commandments of `docker-compose.yaml`, as an advisory save-hook plus an
on-demand audit.

Editing any `docker-compose.y*ml` or `compose.y*ml` runs the checker and prints
findings to stderr. It never blocks an edit.

## What it checks

| ID | Commandment | Severity |
|----|-------------|----------|
| DC-001 | Thou Shalt Not Use `latest` | high |
| DC-002 | Thou Shalt Keep Secrets Out of Version Control | high |
| DC-003 | Thou Shalt Define Explicit Healthchecks | medium |
| DC-004 | Thou Shalt Enforce Resource Limits | high |
| DC-005 | Thou Shalt Isolate Networks | high |
| DC-006 | Thou Shalt Persist State via Named Volumes | medium |
| DC-007 | Thou Shalt Run as Non-Root | medium |
| DC-008 | Thou Shalt Cap Log Output | medium |
| DC-009 | Thou Shalt Keep Configuration DRY | low |
| DC-010 | Thou Shalt Configure Graceful Shutdowns | medium |

Rationale and remedies: [`skills/docker-compose-commandments/references/commandments.md`](skills/docker-compose-commandments/references/commandments.md).
A checker-clean starting point: [`references/compose-template.yaml`](skills/docker-compose-commandments/references/compose-template.yaml).

## Install

```bash
claude plugin install manifest-docker@manifest
```

The hook arms itself on install. No bootstrap required — the checker depends
only on Python 3.10+ and PyYAML, and degrades to a one-line stderr notice if
PyYAML is absent rather than failing the edit.

## Use

```bash
/manifest-docker:docker-compose-commandments   # audit + fix through the skill

# or drive the checker directly
python3 scripts/compose_check.py .           # audit a tree
python3 scripts/compose_check.py . --json    # machine-readable
python3 scripts/compose_check.py . --strict  # CI gate (see exit codes below)
python3 scripts/compose_check.py --list-rules
```

### `--strict` exit codes

| code | meaning |
|------|---------|
| `0` | every target was read and is compliant |
| `1` | files were audited; rules were broken |
| `2` | one or more targets could **not** be audited (unparseable, unreadable, or PyYAML missing) |

`0` is reserved for a verified pass. An unparseable compose file produces zero
findings, and without code `2` that is indistinguishable from clean — which is
how a CI gate goes green without checking anything.

## Suppressing a finding

```yaml
services:
  migrate:
    user: root  # compose-commandments:ignore DC-007 — chowns the data volume at init
```

A bare `# compose-commandments:ignore` suppresses every rule on the line; named
ids suppress only those. For a finding about a *missing* key the marker may sit
anywhere in that service block. `# compose-commandments:ignore-file` anywhere in
the file exempts the whole file — intended for fixtures and teaching examples.

## Relationship to other Manifest skills

- **`/manifest-ops:version-pin` owns image pinning.** DC-001 detects an unpinned image and
  points at it; it does not resolve versions or digests itself, so the two
  cannot drift apart.
- **`/manifest-security:docker-audit-firewall`** covers host firewall rules for a published port.
- **`/manifest-ops:config-validate-native`** validates an application's own config file with
  that application's parser.

## Layout

```text
manifest-docker/
├── config/compose_commandments.yml   # rule registry — ids, severities, remedies
├── hooks/
│   ├── hooks.json                    # PostToolUse: Write|Edit|MultiEdit
│   └── compose_commandments_hook.py  # stdin adapter, always exit 0
├── scripts/
│   ├── compose_check.py              # CLI: config, discovery, bypass, report
│   ├── compose_model.py              # line-tracking loader + shared predicates
│   └── compose_rules.py              # the ten rules, one function each
└── skills/docker-compose-commandments/
```

Adding a rule: add the YAML entry, add `_rule_dc_nnn` to `compose_rules.py`,
register it in `RULES`. Retiring one: mark `retired: true` in the YAML and
delete the function — never reuse an id, because bypass markers in user
repositories cite them by name.
