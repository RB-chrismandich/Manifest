---
name: version-pin
description: Enforce hashed version pins in requirements.txt, docker-compose.yaml, and Dockerfiles — detects loose refs (latest, missing hash, unbounded range), resolves version+hash via native package managers, auto-fixes or warns on save hook. Per-entry bypass supported.
---

# Version Pinning Enforcement

Detect and fix loose dependency references so builds are reproducible and
supply-chain-safe. Pins to a **specific version** (latest stable by default, or
a requested version) and includes an **integrity hash/digest** wherever the
ecosystem supports it.

This skill is backed by `../../runtime/bin/version_pin.sh` relative to this
skill directory. Recognized file types and resolvers are defined in the adjacent
`../../runtime/config/version_pin.json` registry (extensible without code changes).

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
   ../../runtime/bin/version_pin.sh

   # One file, warn-only (no edits) — same mode the hook runs
   ../../runtime/bin/version_pin.sh requirements.txt --check

   # Pin a specific requested version instead of latest stable
   ../../runtime/bin/version_pin.sh requirements.txt --requested requests=2.31.0

   # Limit to one rule
   ../../runtime/bin/version_pin.sh . --rule docker-compose
   ```

2. **Read the report.** Each entry is classified:
   - `violation` — loose; shown with the exact pinned+hashed replacement.
   - `compliant` — already pinned with a hash (left unchanged).
   - `bypassed` — carries the bypass marker (left byte-for-byte unchanged).
   - `unresolved` — version/hash could not be resolved (non-fatal warning; file
     untouched). Common causes: missing native tool, offline, or a required
     hash/digest that could not be obtained (the file is left as-is rather than
     pinned without integrity). A mutable `latest` Docker tag is pinned **by
     digest** (tag preserved, e.g. `postgres:latest@sha256:…`); pass
     `--requested name=VERSION` to also pin a specific version label.

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

The bundle declares an ownership-marked advisory `PostToolUse` (`Write|Edit`)
hook. On supported harnesses it runs the packaged checker in `--check` mode for
recognized files, never blocks, and never edits. Harnesses without native file
hooks expose this on-demand skill and must report `hooks.version-pin=DEGRADED`;
unrelated edits remain quiet.

## Guarantees

- **Idempotent**: a second run on an already-pinned file reports no changes.
- **No silent failures**: unresolvable/unsupported/malformed cases are reported,
  never swallowed, and never leave a partially-rewritten file.
- **Security-sensitive**: this is a supply-chain control (Tier 1); changes to the
  script itself warrant `manifest-workspace:parallel-agent --json --validate --review`
  before merge when that interface is available, or an equivalent inline review
  reported as degraded.
