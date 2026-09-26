# Deploy-Stamp Staleness Nudge — Design

**Date**: 2026-07-03
**Status**: Approved (brainstorm) — pending spec review
**Author**: Claude (brainstormed with Chris)

## Problem

The repo deliberately splits *source* (`configs/`, `.retired skill supply/skills/`) from
*live* (`~/.claude/` and mirrors): edits in the repo do nothing until
`./bootstrap.sh` redeploys. Nothing surfaces the gap between the two — drift is
discovered only when a stale skill or config misbehaves. This has bitten
repeatedly (the `parallel_agent.py` config-deploy gotcha; multiple feature
closeouts with "re-bootstrap still pending").

Existing skills (`deploy-reconcile`, `config-audit`, `deploy-diagnose-drift`)
are reactive investigation tools; none tell you drift exists unprompted.

## Decision Summary

| Decision | Choice |
|----------|--------|
| Direction | Detect + nudge (no auto-redeploy, no symlinks) |
| Trigger | Claude Code `SessionStart` hook, fires in any project |
| Staleness test | Deploy stamp: source-to-source git tree-hash comparison |
| Noise control | Warn only on clean default-branch drift; dedupe once per distinct source hash |

Rejected alternatives: auto-redeploy (deploys fire at surprising times;
mid-branch state could deploy), symlinking live dirs into the clone (live
sessions would track the checked-out branch, leaking feature WIP into all
assistants), live-tree diffing (the deploy is not a plain copy —
`settings.local.json` is merge-preserved, `command_config.yml` gates are
preserved, `services.yml` is generated, graphify skills are toggle-gated — so
the exclude list would have to mirror `deploy.sh` semantics forever, a standing
false-positive risk).

## Component 1: Stamp writer (bootstrap side)

At the end of a successful Claude deploy, write
`~/.claude/config/deploy_stamp` via a `write_deploy_stamp()` helper called in
**both** deploy paths alongside `write_services_config`:

- Fresh/backup-replace path (~line 201): stamp is written normally.
- Merge-mode path (~line 132): the merge path uses
  `rsync --ignore-existing`, so a pre-existing `settings.local.json` is
  **skipped** — meaning a user redeploying via merge would not receive the new
  SessionStart hook from the repo copy. The merge path therefore must (a) call
  `write_deploy_stamp()` too, and (b) ensure the SessionStart hook is present
  in the live `settings.local.json`. Reuse the existing
  `merge_claude_mcp_servers` idempotent-JSON-merge approach: extend it (or add
  a sibling `merge_claude_session_hooks()`) to union the repo's SessionStart
  hook entry into the live file if absent. Without this the nudge is
  dead for every merge-mode redeploy.

The stamp contents:

```
tree_configs=<git rev-parse HEAD:configs>
tree_skills=<git rev-parse HEAD:.retired skill supply/skills>
head_sha=<git rev-parse HEAD>
dirty=<true|false>          # configs/ or .retired skill supply/skills/ had uncommitted changes at deploy time
clone_path=<absolute path of the deploying clone>
deployed_at=<ISO-8601 UTC>
```

- Format: flat `key=value` lines (parseable by both bash and tests without a
  YAML dependency).
- Recording `clone_path` solves clone discovery for the checker — no reliance
  on `MANIFEST_ROOT` being exported in the hook's environment.
- `dirty` is scoped to the two deploy-source paths only —
  `git status --porcelain -- configs .retired skill supply/skills` — **not** the whole
  worktree. This mirrors the checker's step 4 exactly; an unrelated
  uncommitted change (a WIP test, a doc edit) must not mark the stamp dirty,
  or step 5 would nudge on a clean-main deploy whose configs/skills were in
  fact fresh.
- If the deploying directory is not a git repo (e.g. tarball copy), skip the
  stamp entirely; the checker then stays silent (fail-open).
- The stamp is repo-owned output like `services.yml`: regenerated on every
  deploy, never hand-edited, and excluded from merge-preservation.

## Component 2: Checker (deployed side)

New script `configs/claude/scripts/deploy_stamp_check.sh`, deployed to
`~/.claude/scripts/`, registered as a `SessionStart` hook in
`configs/claude/settings.local.json` (the first SessionStart entry in that
file). SessionStart is a new event key for this settings file (it currently
has only `PreToolUse`/`PostToolUse`/`UserPromptSubmit`).

Also add `Bash(~/.claude/scripts/deploy_stamp_check.sh:*)` to
`permissions.allow`. This is **not** required for the hook to run — harness-fired
hooks don't gate on `permissions.allow` (3 of the 5 existing hooks have no allow
entry and run fine) — but it matches the pattern of 2 of the 5 existing hooks
and costs nothing, so include it for consistency.

Logic, in order — every early exit is a silent `exit 0`:

1. Stamp file missing or unparseable → exit (pre-stamp deploys never nudge).
2. `clone_path` missing on disk or not a git repo → exit (clone moved/deleted).
3. In the clone: current branch ≠ default branch → exit (feature-branch drift
   is expected WIP). Default branch resolved from
   `refs/remotes/origin/HEAD`, falling back to `main`.
4. Worktree dirty (`git status --porcelain` non-empty for `configs/` or
   `.retired skill supply/skills/`) → exit (uncommitted WIP).
5. Compute current `git rev-parse HEAD:configs HEAD:.retired skill supply/skills` in the
   clone. Both match the stamp's tree hashes **and** stamp `dirty=false` →
   exit (deploy is fresh). A `dirty=true` stamp never matches — the stamp's
   tree hashes did not reflect what was actually deployed, so the next
   clean-main check re-nudges once and the next deploy rewrites a clean stamp.
6. Dedupe: state file `$MANIFEST_STATE_ROOT/deploy_stamp_warned`
   (default `~/.manifest/deploy_stamp_warned`) holds the last-warned combined
   hash. Current combined hash equals it → exit.
7. Emit the nudge to stdout and write the combined hash to the state file.

Using git tree SHAs instead of hashing file contents makes the comparison
O(1) subprocess calls (a few milliseconds, no tree walk). It is sound
precisely because step 4 already requires a clean tree, so HEAD trees equal
worktree content.

### Nudge format

```
⚠ Manifest deploy is stale: <clone_path> (main @<short-sha>) has changed
configs/ or skills since the last deploy on <deployed_at>.
Run ./bootstrap.sh in <clone_path> to redeploy.
```

SessionStart hook stdout becomes session context — visible to the user and
actionable by Claude in whatever project the session starts in.

## Error handling

- The script must never block or fail a session start: every error path exits
  0. `set -euo pipefail` is not used at top level for this reason; individual
  commands are `|| exit 0` guarded (or the script traps ERR to exit 0).
- Diagnostics route through the canonical `err() { echo "deploy_stamp_check.sh: $*" >&2; }`
  and only fire under a `DEPLOY_STAMP_DEBUG=1` env var — a hook that prints to
  stderr on every session would itself be noise.
- `--help` is handled (usage + flags, ≤15 lines, exit 0) since the script is
  user-invocable for debugging; the help path runs before any stamp/git
  lookup per cli-audit-help.

## Out of scope (YAGNI)

- Auto-redeploy on drift.
- Hooks for Cursor/Gemini/Codex/Antigravity mirrors — the Claude SessionStart
  hook covers where the user actually works; mirrors redeploy from the same
  `./bootstrap.sh` run anyway.
- Multi-clone arbitration: the stamp records the last-deploying clone only.
- Age-gating or re-warning cadence beyond once-per-hash.
- Detecting manual edits to the live `~/.claude` tree (user-owned;
  `deploy-reconcile` covers that direction).
- Re-stamping from `sync-skills`. `sync-skills.sh` is a *partial* deploy: it
  rsyncs only `.retired skill supply/skills/` into `~/.claude/skills` and does not ship
  `configs/`, scripts, or `services.yml`, so it deliberately does not write the
  stamp. Consequence: after a skills-only `sync-skills` on a clean default
  branch, the checker may fire once ("run `./bootstrap.sh`") even though the
  skills are already live — which is technically correct (a full bootstrap
  deploy *is* stale) but can read as a false positive to a skill developer. The
  nudge is harmless (bootstrap is idempotent and re-stamps) and dedupes per
  hash. A future `sync-skills.sh` enhancement could patch just `tree_skills` in
  the existing stamp to close this window; intentionally deferred so the checker
  never has to model partial-deploy semantics.

## Testing

Bats (new file `tests/bats/deploy_stamp.bats`, following existing fixture
patterns — temp git repo with `configs/` + `.retired skill supply/skills/`):

Stamp writer:
1. Successful deploy writes a stamp with all six keys and correct tree hashes.
2. Uncommitted change under `configs/` at deploy time → stamp `dirty=true`.
2b. Uncommitted change OUTSIDE `configs/`+`.retired skill supply/skills/` (e.g. a WIP
    file under `tests/`) → stamp `dirty=false` (scope isolation; guards the
    finding-3 false positive).
3. Non-git source dir → no stamp written, deploy still succeeds.
4. Merge-mode deploy path also writes the stamp AND unions the SessionStart
   hook into a pre-existing live `settings.local.json` that lacked it
   (guards the finding-1 gap).

Checker (each asserts silent exit 0 unless noted):
5. No stamp file.
6. `clone_path` does not exist.
7. Clone on a feature branch.
8. Clone on main with dirty `configs/`.
9. Hashes match, `dirty=false` stamp.
10. Hashes differ on clean main → nudge emitted (stdout non-empty, exit 0),
    state file written.
11. Same drift, second run → silent (dedupe).
12. New commit after a warned drift → nudges again (new hash).
13. `dirty=true` stamp with matching hashes → nudges (stamp untrusted).
14. `--help` exits 0 with usage, in a clean env (no stamp, no git).

Plus `shellcheck` via the existing changed-file gate, and hook JSON validity
via the existing settings checks.

## Files touched

| File | Change |
|------|--------|
| `configs/claude/scripts/deploy_stamp_check.sh` | New checker script |
| `bootstrap/lib/deploy.sh` | `write_deploy_stamp()` helper called in both deploy paths; merge-mode also unions the SessionStart hook into the live `settings.local.json` (skipped by `rsync --ignore-existing`) |
| `configs/claude/settings.local.json` | Add SessionStart hook entry + `permissions.allow` entry (consistency) |
| `tests/bats/deploy_stamp.bats` | New test file |
| `docs/COMMANDS.md` / guides | Only if the regen chain requires it (no new skill, so likely untouched) |
