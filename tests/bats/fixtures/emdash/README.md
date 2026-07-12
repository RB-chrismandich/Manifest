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

home-corrupted-hooks/.claude/                 # variant of home/ used for the NEGATIVE-path
├── ...                                       #   test: settings.json is identical to
├── settings.json                             #   home/settings.json, but ...
└── settings.json.emdash-merged               #   ... this sibling genuinely DROPS the
                                              #   PostToolUse (version_pin_hook.sh) entry ->
                                              #   coexistence.manifest_hooks_preserved == false

worktree-corrupted-permissions/               # variant of worktree/ used for the NEGATIVE-path
├── ...                                       #   test: settings.local.json is identical to
├── .claude/settings.local.json               #   worktree/settings.local.json, but ...
└── .claude/settings.local.json.emdash-merged #   ... this sibling genuinely DROPS three
                                              #   allow entries ->
                                              #   coexistence.worktree_permissions_intact == false
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
post-merge state and the plain file as the pre-merge baseline, and in that case
genuinely diffs the two — this is what makes `manifest_hooks_preserved` /
`worktree_permissions_intact` a real, deterministic assertion here. In a live
`/env-check` run no sibling exists, so there is no independent baseline to diff
(marker detection for `emdash_hook_detected` still works, since that only
inspects the current file's content, not a diff). Diffing a file against
itself would always report "preserved/intact" even if something had actually
been dropped, so the probe reports `null`/`unverified` for those two fields in
that case rather than a false `true` — see the "Coexistence assertion" section
of `contracts/inheritance-probe.md`.

## Injected env (reproduced by the bats test, not stored here)

emdash's PTY sets `HOME`, `PATH`, and `EMDASH_HOOK_PORT` / `EMDASH_PTY_ID` /
`EMDASH_HOOK_NONCE`. The test exports these when invoking the probe to confirm
their presence does not degrade resolution; the `EMDASH_HOOK_PORT` variable also
appears in the merged fixture's hook command. Real ACP runtime hook-firing is
validated by the manual smoke (quickstart.md), not this fixture.

## Negative-path fixtures (`*-corrupted-*`)

`home/` and `worktree/` above only demonstrate the PASS (tri-state `1`,
verified-preserved) path. `home-corrupted-hooks/` and
`worktree-corrupted-permissions/` are paired, single-difference variants that
exercise the verified-corruption (tri-state `0`) path instead, each swapped in
for the passing fixture on ONE side only (the other side stays on the passing
`home/` or `worktree/` fixture) so the resulting `DEGRADED` verdict is
attributable to exactly one coexistence check:

- **`home-corrupted-hooks/.claude/settings.json.emdash-merged`** genuinely
  omits the `PostToolUse` (`version_pin_hook.sh`) hook present in its own
  `settings.json` baseline — a real diff against a real sibling, not an
  absent one. Paired with the passing `worktree/` fixture, this yields
  `coexistence.manifest_hooks_preserved == false`, D3 `FAIL`, and verdict
  `DEGRADED` (exit 1).
- **`worktree-corrupted-permissions/.claude/settings.local.json.emdash-merged`**
  genuinely drops three `allow` entries present in its own
  `settings.local.json` baseline. Paired with the passing `home/` fixture,
  this yields `coexistence.worktree_permissions_intact == false`, D3 `FAIL`,
  and verdict `DEGRADED` (exit 1).

Together with the `home`/`worktree` pairing (tri-state `1`) and a live run
with no `.emdash-merged` sibling (tri-state `2`, unverifiable — see above),
these two negative fixtures exercise all three tri-state values the
coexistence checks can produce.

## Ground-truth caveat

The exact bytes emdash writes MUST be confirmed against a real emdash spawn (the
manual smoke). If reality differs, update the `.emdash-merged` variants here.
