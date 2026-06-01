---
name: version-pin
description: |
  Enforce specific, hashed version pins in dependency files (requirements.txt,
  docker-compose.yaml, Dockerfiles). Detects loose references (latest, missing
  version, unbounded range, missing hash), resolves a specific version plus
  integrity hash via native package managers, and auto-fixes on demand or
  warns on the save hook. Supports an explicit per-entry bypass.
---

# Version Pinning Enforcement

Detect and fix loose dependency references so builds are reproducible and
supply-chain-safe. Pins to a **specific version** (latest stable by default, or
a requested version) and includes an **integrity hash/digest** wherever the
ecosystem supports it.

This skill is backed by `~/.claude/scripts/version_pin.sh`. The recognized file
types and their resolvers are defined in the `version_pin` block of
`config/command_config.yml` (extensible without code changes).

## When to use

- A `requirements.txt`, `docker-compose.yaml`/`.yml`, or `Dockerfile` references
  a dependency as `latest`, with no version, an unbounded range, or no hash.
- You want to audit or pin every recognized file in a tree.
- The automatic save hook reported a violation and you want to apply the fix.

## Task

1. **Run the script** against the target. Default (on-demand) mode rewrites
   files in place; `--check` is warn-only (no edits) and is what the save hook
   uses.

   ```bash
   # Audit + auto-fix every recognized file in the working tree
   ~/.claude/scripts/version_pin.sh

   # One file, warn-only (no edits) — same mode the hook runs
   ~/.claude/scripts/version_pin.sh requirements.txt --check

   # Pin a specific requested version instead of latest stable
   ~/.claude/scripts/version_pin.sh requirements.txt --requested requests=2.31.0

   # Limit to one rule
   ~/.claude/scripts/version_pin.sh . --rule docker-compose
   ```

2. **Read the report.** Each entry is classified:
   - `violation` — loose; shown with the exact pinned+hashed replacement.
   - `compliant` — already pinned with a hash (left unchanged).
   - `bypassed` — carries the bypass marker (left byte-for-byte unchanged).
   - `unresolved` — version/hash could not be resolved (non-fatal warning; file
     untouched). Common causes: missing native tool, offline, or a mutable
     `latest` tag with no inferable version (supply `--requested`).

3. **Apply or confirm.** On-demand runs already rewrote the file. If you ran
   `--check`, re-run without `--check` (or with `--requested` as needed) to apply.

4. **Bypass intentional exceptions.** Add a trailing comment marker to the line:

   ```text
   somepkg            # version-pin:ignore  (reason: vendored build)
   ```

## Resolution

By default the script shells out to native tooling (`pip`/`pip-compile`,
`docker manifest inspect`). To customize resolution (e.g. an internal mirror or
deterministic CI), set `VERSION_PIN_RESOLVER` to an executable called as
`RESOLVER <ecosystem> <name> <current> <requested>` that prints
`<version><TAB><hash>` or exits non-zero when unresolved.

## Automatic hook (warn-only)

The skill is wired as a `PostToolUse` (`Write|Edit`) hook in
`settings.local.json` via `~/.claude/scripts/version_pin_hook.sh`. On save of a
recognized file it runs `version_pin.sh --check` (advisory, never blocks, never
edits) and prints any violations. The wrapper pre-filters by file name so
unrelated edits stay quiet.

## Guarantees

- **Idempotent**: a second run on an already-pinned file reports no changes.
- **No silent failures**: unresolvable/unsupported/malformed cases are reported,
  never swallowed, and never leave a partially-rewritten file.
- **Security-sensitive**: this is a supply-chain control (Tier 1); changes to the
  script itself warrant parallel-agent review before merge.
