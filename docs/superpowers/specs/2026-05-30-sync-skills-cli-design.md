# sync-skills CLI Design

**Date:** 2026-05-30
**Status:** Approved
**Scope:** Developer-workflow skill sync — `sync-skills` native CLI command

---

## Problem

Adding or editing a skill in `.retired skill supply/skills/` currently requires running `./bootstrap.sh`
to push the change to `~/.claude/skills/` and other home targets. Bootstrap is a full machine
provisioning tool; it is too heavy for a daily edit→sync loop. Developers need a fast,
globally-accessible command that syncs skills without re-running bootstrap.

---

## Goal

A native CLI command (`sync-skills`) available from any directory that:

1. Syncs `.retired skill supply/skills/` to all home targets (`~/.claude/`, `~/.cursor/`, `~/.gemini/`,
   `~/.codex/`).
2. Also runs `retired skill supply sync` for the project-scoped Copilot target (`.github/skills/`).
3. Requires no manual maintenance of the rsync logic — retired skill supply is the known application;
   rsync is the implementation detail inside a thin wrapper.

---

## Architecture

```
Manifest repo
└── scripts/sync-skills.sh        ← source (new file)

Bootstrap
├── bootstrap/lib/auth.sh         ← extend configure_shell_profile_state
│                                    to write MANIFEST_ROOT export
└── bootstrap/lib/deploy.sh       ← add deploy_sync_skills()
                                     copies script + ensures ~/.local/bin on PATH

Runtime (after bootstrap)
└── ~/.local/bin/sync-skills      ← deployed executable, runs from anywhere
```

**Data flow:**

```
edit .retired skill supply/skills/my-skill/SKILL.md
          ↓
sync-skills  (any directory)
          ↓  reads $MANIFEST_ROOT, cd to repo
          ├── retired skill supply sync    →  .github/skills/      (Copilot)
          └── rsync ×1–4        →  ~/.claude/skills/     (always)
                                   ~/.cursor/skills/      (if dir exists)
                                   ~/.gemini/skills/      (if dir exists)
                                   ~/.codex/skills/       (if dir exists)
```

Antigravity is covered automatically — bootstrap creates `~/.antigravity/skills` as a symlink
to `~/.claude/skills/`, so it inherits every rsync update without a separate target.

**Relationship to bootstrap:** `deploy_home_skills` in bootstrap remains for cold install (additive,
no `--delete` — safe when merging into an existing home dir). `sync-skills` uses `--delete` because
it is designed for iteration: if a skill is removed from the repo, it should disappear from all
targets.

---

## Components

### `scripts/sync-skills.sh` (new)

```bash
#!/usr/bin/env bash
set -euo pipefail

[[ -z "${MANIFEST_ROOT:-}" ]] && { echo "Error: MANIFEST_ROOT not set. Re-run bootstrap.sh." >&2; exit 1; }
[[ ! -d "$MANIFEST_ROOT" ]]  && { echo "Error: MANIFEST_ROOT '$MANIFEST_ROOT' not found." >&2; exit 1; }

SKILLS_SRC="$MANIFEST_ROOT/.retired skill supply/skills"
[[ ! -d "$SKILLS_SRC" ]] && { echo "Error: skills source not found: $SKILLS_SRC" >&2; exit 1; }

# Copilot sync via retired skill supply (warn and continue if not installed)
if command -v retired skill supply > /dev/null 2>&1; then
    (cd "$MANIFEST_ROOT" && retired skill supply sync) || echo "Warning: retired skill supply sync failed — continuing"
else
    echo "Warning: retired skill supply not installed — skipping Copilot sync"
fi

# Home targets — parallel rsync so total time = slowest single target
rsync -a --delete "$SKILLS_SRC/" "$HOME/.claude/skills/" &
for dir in "$HOME/.cursor/skills" "$HOME/.gemini/skills" "$HOME/.codex/skills"; do
    [[ -d "$dir" ]] && rsync -a --delete "$SKILLS_SRC/" "$dir/" &
done
wait
```

Key decisions:
- `~/.claude/skills/` is always synced; IDE targets only if the directory exists.
- `--delete` propagates skill removals. Bootstrap's `deploy_home_skills` stays additive.
- Parallel `&` + `wait` bounds total time to the slowest single target.
- `retired skill supply sync` runs in a subshell so the calling script's `cwd` is never changed.

### `bootstrap/lib/auth.sh` — extend `configure_shell_profile_state`

Add `MANIFEST_ROOT` export after the existing `MANIFEST_STATE_ROOT` block. Unlike
`MANIFEST_STATE_ROOT` (which has a safe per-machine default), `MANIFEST_ROOT` must store the
actual checkout path and must be updated if bootstrap is re-run from a different location.

Cross-platform safe update (avoids `sed -i` BSD/GNU incompatibility on macOS):

```bash
# Remove any existing MANIFEST_ROOT line, then append current path
if [[ -f "$profile_file" ]]; then
    grep -v 'export MANIFEST_ROOT=' "$profile_file" > "${profile_file}.tmp" || true
    mv "${profile_file}.tmp" "$profile_file"
fi
echo "export MANIFEST_ROOT=\"$SCRIPT_DIR\"" >> "$profile_file"
```

### `bootstrap/lib/deploy.sh` — add `deploy_sync_skills()`

Called at the end of `deploy_configs` (after `sync_retired skill supply_targets`). Depends on
`SHELL_PROFILE_FILE` being set, which `configure_shell_profile_state` in `auth.sh` already
provides — bootstrap calls that function before `deploy_configs`.

```bash
deploy_sync_skills() {
    print_step "Deploying sync-skills CLI..."
    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/scripts/sync-skills.sh" "$HOME/.local/bin/sync-skills"
    chmod +x "$HOME/.local/bin/sync-skills"

    # Ensure ~/.local/bin is on PATH in shell profile (idempotent)
    if ! grep -Fq ".local/bin" "$SHELL_PROFILE_FILE" 2>/dev/null; then
        {
            echo ""
            echo "# ~/.local/bin for user-installed tools (managed by bootstrap.sh)"
            echo 'export PATH="$HOME/.local/bin:$PATH"'
        } >> "$SHELL_PROFILE_FILE"
    fi

    # Fix PATH for the current bootstrap session (PATH Catch-22)
    export PATH="$HOME/.local/bin:$PATH"

    print_success "Deployed sync-skills to $HOME/.local/bin/sync-skills"
}
```

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `MANIFEST_ROOT` not set | Fatal error with re-run hint |
| `MANIFEST_ROOT` path missing | Fatal error with path in message |
| `.retired skill supply/skills/` missing | Fatal error |
| `retired skill supply` not installed | Warning, skip Copilot sync, continue |
| `retired skill supply sync` fails | Warning, continue with home targets |
| IDE target dir missing | Skip silently (`[[ -d ]]` guard) |
| `~/.claude/skills/` missing | rsync creates it |

---

## Testing

New BATS tests in `tests/bats/`:

- `sync-skills.sh` exits non-zero and prints a clear error when `MANIFEST_ROOT` is unset.
- `sync-skills.sh` exits non-zero when `MANIFEST_ROOT` points to a non-existent directory.
- `sync-skills.sh` runs rsync home targets when `retired skill supply` is not on PATH.
- `configure_shell_profile_state` writes `MANIFEST_ROOT` to the shell profile.
- `configure_shell_profile_state` updates `MANIFEST_ROOT` on re-run with a new path (no duplicate lines).
- `deploy_sync_skills` copies script to `~/.local/bin/sync-skills` and makes it executable.
- `deploy_sync_skills` adds `~/.local/bin` to PATH in shell profile (idempotent).

---

## Out of Scope

- Windows support (bootstrap is macOS/Linux only).
- `sync-skills` managing bootstrap's initial cold-install (`deploy_home_skills` owns that).
- Parallelising `retired skill supply sync` with the rsync targets (retired skill supply must run from
  `$MANIFEST_ROOT`; the rsync targets are independent — mixing them adds complexity for
  minimal gain).
