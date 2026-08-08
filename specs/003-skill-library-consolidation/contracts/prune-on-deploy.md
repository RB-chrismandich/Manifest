# Contract: Prune-on-Deploy (skills)

**Applies to**: `deploy_home_skills()` (bootstrap/lib/common.sh) and
`sync-skills.sh` (already compliant).

Behavior:
1. After a deploy/sync run, every skill this tool previously deployed that is
   now absent from `.retired skill supply/skills/` is removed from the target
   (manifest-scoped pruning via the `.deployed-skills` manifest — NOT
   `rsync --delete` full mirroring). Skills added to the target by other
   means are preserved. Safety bounds: an empty source never prunes
   (requires >=1 source skill); manifest entries are validated as plain
   single-level names so a corrupted manifest cannot drive deletion outside
   the target.
2. Scope bound: deletion applies ONLY within the skills deploy directory,
   and only to manifest-listed names. No deploy of skills may remove or
   modify any path outside it.
3. Idempotence: a second consecutive run makes zero changes (Constitution V).
4. Symlink targets (Cursor/Gemini/Codex/Antigravity point at the home skills
   dir) converge automatically; `.github/skills` remains retired skill supply-owned and
   out of this contract's scope.

Test obligations (tests/bats/deploy_skills.bats):
- deploy → delete skill in source → redeploy → skill absent in target
- file outside the skills dir in the target tree survives a deploy
- a skill present in the target but never deployed by this tool (not in the
  manifest) survives a deploy
- double-deploy is a no-op (rsync reports no transfers)
