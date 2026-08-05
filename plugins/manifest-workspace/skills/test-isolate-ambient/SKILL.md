---
name: test-isolate-ambient
description: Use before verifying Manifest deploy, hook, or installer behaviour — a pass against your real ~/.claude, settings.json, or checked-out repo proves nothing; the ambient state IS the fixture. Provides isolation handles (TARGET_DIR, ISSUE_HOOKS_SETTINGS, throwaway clone) and the rule for making the varying thing vary.
---

# Isolate Ambient State Before Verifying

A verification that runs against your own machine's state is not a verification —
it is a coincidence. Three defects shipped from this repo in one session, each
green locally and wrong elsewhere, all from the same root cause:

| Claim | Why it was false |
|---|---|
| "snapshots reproduce byte-identically" | run twice in ten seconds; the append-only corpus had not grown |
| "`parallel_agent.py --help` works" | `configs/claude/.venv` existed locally, not in CI |
| "the hook de-dup matches" | tested the bare-path shape, not the interpreter-prefixed one the repo actually uses |
| "the behind-check fires" | every test ran on a slash-free init branch; `release/v2` silently no-opped |

## The rule

**Make the varying thing vary inside the check.** If the behaviour depends on a
corpus growing, a branch name's shape, a file's presence, or a command's prefix,
the test must change that thing between the two observations. A check that
cannot fail on the broken code is not a check.

Corollary: prefer a **mechanically-derived** exemption over a hand-maintained
name list. Deriving "is this a shim?" from its `_manifest_shim` import exempts
the next shim automatically; listing `parallel_agent.py` by name broke the build
the day it stopped satisfying the gate.

## Isolation handles (this repo)

Do not rebuild these — they exist and are exercised by the suite.

### 1. Deploy: redirect every target away from `$HOME`

`bootstrap/lib/deploy.sh` reads its destinations from the environment, so a
sandbox needs no `HOME` games and no root. Stub the secondary deploys — they
want network, other CLIs, and unrelated configs.

```bash
export SCRIPT_DIR="$REPO_ROOT"
export TARGET_DIR="$SANDBOX/home/.claude"
export CURSOR_TARGET_DIR="$SANDBOX/home/.cursor"
export GEMINI_TARGET_DIR="$SANDBOX/home/.gemini"
export CODEX_TARGET_DIR="$SANDBOX/home/.codex"
export ANTIGRAVITY_TARGET_DIR="$SANDBOX/home/.antigravity"
export MANIFEST_OUTPUT_DIR="$SANDBOX/home/.manifest/outputs"
export FORCE=true
source "$REPO_ROOT/bootstrap/lib/deploy.sh"
write_services_config() { :; }; deploy_cursor_configs() { :; }
deploy_gemini_configs() { :; }; deploy_codex_configs() { :; }
deploy_antigravity_configs() { :; }
deploy_sync_skills() { :; }
```

Worked example: `tests/bats/deploy_skills.bats`. For a single function
(`deploy_home_skills SRC DEST`), pass the two dirs directly — no env at all.

> A sub-agent cannot run a real `./bootstrap.sh` redeploy of `~/.claude` (the
> safety classifier reads it as self-modification). Verify in a sandbox and hand
> the real redeploy to the user.

### 2. Hook installer: redirect the settings file

`install_issue_hooks.sh` resolves `SETTINGS_FILE` from `ISSUE_HOOKS_SETTINGS`,
falling back to `$HOME/.claude/settings.json`. Set it and your real settings are
never touched.

```bash
export ISSUE_HOOKS_SETTINGS="$TMP/settings.json"
```

Assert on **shape**, not on a count you eyeballed: this repo registers hooks
interpreter-prefixed (`bash /path/hook.sh`), so a de-dup test that only builds
the bare-path form passes while the real registration double-installs. Seed
both shapes. Worked example: `tests/bats/install_issue_hooks.bats`.

### 3. Drift hook: build a throwaway clone, not a reference to yours

`deploy_stamp_check.sh` needs a real git repo whose `refs/remotes/origin/*` you
control. Build it; never point the stamp at your working clone (the first
attempt at this got it wrong precisely there).

```bash
CLONE="$TMP/clone"
mkdir -p "$CLONE/configs/claude" "$CLONE/.apm/skills/demo"
echo x > "$CLONE/configs/claude/CLAUDE.md"
echo y > "$CLONE/.apm/skills/demo/SKILL.md"
git -C "$CLONE" init -q
git -C "$CLONE" config user.email t@t.test && git -C "$CLONE" config user.name test
git -C "$CLONE" add -A && git -C "$CLONE" commit -qm init
git -C "$CLONE" symbolic-ref refs/remotes/origin/HEAD \
    "refs/remotes/origin/$(git -C "$CLONE" rev-parse --abbrev-ref HEAD)"
```

To simulate "someone else fetched, you did not": commit forward, point
`refs/remotes/origin/<branch>` at the new tip, then `git reset --hard` back.
Redirect the warn-dedup state with `MANIFEST_STATE_ROOT="$FHOME/.manifest"` and
turn on diagnostics with `DEPLOY_STAMP_DEBUG=1`. Worked example:
`tests/bats/deploy_stamp.bats`.

## Procedure

1. **Name the ambient input.** What on this machine, absent elsewhere, could make
   the check pass? A venv, a corpus, a branch name, an existing settings file, a
   fetched ref, a deployed `~/.claude`.
2. **Take the handle above** if one exists; otherwise add an env override to the
   script rather than `cd`-ing into a fake `HOME`.
3. **Vary it inside the check** — two observations with the input genuinely
   different between them.
4. **Prove the check is a gate.** Revert the fix, confirm the test goes red,
   restore, confirm green. An unproven test is an assertion about an assertion.
5. **Report what you actually ran.** Command and outcome, not "verified".

> Sub-agents: not used — building one fixture is a single sequential unit.

## Related

- `superpowers:verification-before-completion` — evidence before success claims (the general rule)
- `test-pin-bug` — pinning a known-buggy value without breaking on the fix
- `test-vary-fixtures` — the same "make it vary" rule for statistical fixtures
- `cli-audit-help` — `--help` must work before any config/state lookup, verified in a clean env
- `false-green-check-audit` — a skipped check must never render as a green pass
