# Contract: Prune-on-Deploy (skills)

**Applies to**: `deploy_home_skills()` (bootstrap/lib/common.sh) and
`sync-skills.sh` (already compliant).

Behavior:
1. After a deploy/sync run, the skills deploy directory is byte-identical in
   membership to `.skillshare/skills/` — skills absent from the source are
   removed from the target (`rsync -a --delete` semantics).
2. Scope bound: deletion applies ONLY within the skills deploy directory.
   No deploy of skills may remove or modify any path outside it.
3. Idempotence: a second consecutive run makes zero changes (Constitution V).
4. Symlink targets (Cursor/Gemini/Codex/Antigravity point at the home skills
   dir) converge automatically; `.github/skills` remains skillshare-owned and
   out of this contract's scope.

Test obligations (tests/bats/deploy_skills.bats):
- deploy → delete skill in source → redeploy → skill absent in target
- file outside the skills dir in the target tree survives a deploy
- double-deploy is a no-op (rsync reports no transfers)
