# emdash launch-env test fixture

Synthetic reproduction of how the [emdash](https://github.com/generalaction/emdash)
desktop app launches a Manifest-configured Claude Code agent in a git worktree.
Feeds `configs/claude/scripts/emdash_inherit_check.sh` (the inheritance probe)
from `tests/bats/emdash_inheritance.bats`. Maps to data-model **E3** of
`specs/483-emdash-support/`.

Nothing here is deployed — these are inert test inputs. The layout is faithful
to the repo's REAL split (spec-review F3): **hooks live HOME-side**
(`~/.claude/settings.json`); the tracked repo `.claude/settings.local.json`
holds **permissions only** (no hooks).

## Layout

```text
emdash/
├── home/.claude/                          # fake $HOME/.claude — the Manifest home deploy
│   ├── CLAUDE.md                          # D5 home orchestration guide
│   ├── skills/env-check/SKILL.md          # D1 skills (>=1 SKILL.md reachable)
│   ├── agents/developer.md                # D2 home-side subagent
│   ├── settings.json                      # D3 Manifest hooks + D4 mcpServers (baseline)
│   └── settings.json.emdash-merged        # D3 emdash Stop hook appended ALONGSIDE the
│                                          #    pre-existing Manifest Stop hook (audit_log.sh)
│                                          #    -> hook-PRESERVATION assertion
└── worktree/                              # fake repo checkout in an emdash worktree
    ├── CLAUDE.md                          # D5 repo orchestration guide
    ├── AGENTS.md                          # D6 repo guide
    └── .claude/
        ├── agents/reviewer.md             # D2 repo-side subagent
        ├── settings.local.json            # PERMISSIONS ONLY (no hooks) — baseline
        └── settings.local.json.emdash-merged  # emdash Stop hook appended ALONGSIDE the
                                           #    permissions block -> permissions-NOT-CORRUPTED
                                           #    assertion
```

## The two `.emdash-merged` variants

emdash appends its own hook — `{ "type":"command", "command":"curl
http://127.0.0.1:$EMDASH_HOOK_PORT/hook", <EMDASH_MARKER> }` — to a hook-event
array (observed shape: `Stop: [emdashHook, userHook]`) and tags it with an
idempotency marker. The fixture encodes that marker as the field
`"__emdashMarker": "emdash-managed-hook"` (the probe detects it via the marker
substring or the `EMDASH_HOOK_PORT` command; override with `EMDASH_MARKER`).

- **`home/.claude/settings.json.emdash-merged`** — the emdash `Stop` entry sits
  next to the pre-existing Manifest `Stop` hook (`audit_log.sh`) and all other
  Manifest hook events are unchanged. The probe asserts every Manifest hook
  survives the append → `coexistence.manifest_hooks_preserved == true`.
- **`worktree/.claude/settings.local.json.emdash-merged`** — the emdash `Stop`
  hook is added while the `permissions` block is byte-for-byte unchanged. The
  probe asserts the permissions block is not corrupted →
  `coexistence.worktree_permissions_intact == true`.

The probe treats the `.emdash-merged` sibling (when present) as the simulated
post-merge state and the plain file as the pre-merge baseline. In a live
`/env-check` run no sibling exists, so the probe reads the real in-place file as
both baseline and merged (marker detection still works).

## Injected env (reproduced by the bats test, not stored here)

emdash's PTY sets `HOME`, `PATH`, and `EMDASH_HOOK_PORT` / `EMDASH_PTY_ID` /
`EMDASH_HOOK_NONCE`. The test exports these when invoking the probe to confirm
their presence does not degrade resolution; the `EMDASH_HOOK_PORT` variable also
appears in the merged fixture's hook command. Real ACP runtime hook-firing is
validated by the manual smoke (quickstart.md), not this fixture.

## Ground-truth caveat

The exact bytes emdash writes MUST be confirmed against a real emdash spawn (the
manual smoke). If reality differs, update the `.emdash-merged` variants here.
