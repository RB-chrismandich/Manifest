# Contract: Bootstrap Flags

**Surface**: `bootstrap.sh` / `bootstrap/lib/config.sh` CLI

## New flags

| Flag | Effect | Default |
|------|--------|---------|
| `--enable-graphify` | Force graphify on; sets `ENABLE_GRAPHIFY=true`, `GRAPHIFY_SET=true` | graphify is on by default |
| `--disable-graphify` | Force graphify off; sets `ENABLE_GRAPHIFY=false`, `GRAPHIFY_SET=true` | — |

## Guarantees

- **Default-on**: with neither flag, a standard `./bootstrap.sh` run enables graphify (installs + deploys).
- **Flag precedence**: an explicit flag (`GRAPHIFY_SET=true`) overrides any value in an existing `services.yml`.
- **Persistence**: the resolved value is written to `~/.claude/config/services.yml` and honored on later flag-less runs.
- **Help**: `./bootstrap.sh --help` lists both flags under Service Toggles (`--disable-graphify` documented as the opt-out; `--enable-graphify` for re-enable). ≤ existing help style.
- **Reconfigure**: `--reconfigure` shows graphify `old → new` state alongside other services.

## Acceptance (maps to spec)

- `./bootstrap.sh` (no flag) → graphify enabled (US1, SC-001).
- `./bootstrap.sh --disable-graphify` → no graphify install/deploy, no uv added, no creds requested (US2-AC1, SC-002).
- `./bootstrap.sh --disable-graphify` then `./bootstrap.sh` (no flag) → still disabled (US2-AC3, honors persisted value).
