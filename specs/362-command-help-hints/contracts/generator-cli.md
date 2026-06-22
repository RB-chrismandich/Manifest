# Contract: Catalog Generator + Doc Renderer

Two cooperating scripts under `configs/claude/scripts/`. Build the machine catalog from the
source of truth and render the committed reference doc.

## `command_catalog.py`

```text
command_catalog.py [--json] [--platform <name>]
```

- Walks `.skillshare/skills/*/SKILL.md` (symlink-following per repo convention).
- Emits the catalog (see `catalog-schema.md`). `--json` → machine output; default → human summary.
- `--platform` sets the active platform for `availability` resolution (default: detect).
- **Exit**: `0` ok; non-zero on malformed/duplicate/empty skill (names the offending file).

## `generate_commands_doc.py`

```text
generate_commands_doc.py [--check]
```

| Mode | Behavior | Exit |
|------|----------|------|
| (default) | Render catalog → overwrite `docs/COMMANDS.md` | `0` written |
| `--check` | Render in memory, diff vs committed `docs/COMMANDS.md`, write nothing | `0` in-sync · `1` drift (prints diff) · `2` error |

## Contract guarantees

- **Idempotent** (Constitution V): re-running default mode with no source change is a no-op diff.
- **Zero drift** (FR-004/SC-002): a freshly added/removed skill changes the render; `--check` fails until regenerated. Wired into CI (`commands_doc_drift.bats`).
- **Budget** (FR-009/SC-006): the catalog table injected into agent guides is sized to pass `context_budget`; renderer supports a compact form for always-loaded targets.
- **`--help`** succeeds before any filesystem/config dependency (repo convention).
