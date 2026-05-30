# Retire `parallel_agent.sh` — Design

**Date**: 2026-05-30
**Status**: Approved for planning
**Issue**: #256
**Topic**: Remove the deprecated `configs/claude/scripts/parallel_agent.sh`,
repointing all references to the maintained `parallel_agent.py`.

---

## Goal

`parallel_agent.sh` (1939 lines) is marked DEPRECATED in its own header and was
superseded by `parallel_agent.py` (reached feature parity in `9ff5b1e`). It is
still the live entrypoint referenced across the repo, and it is the source of
the cosmetic shellcheck noise that the CI `-S warning` policy works around.
Retire it: repoint every reference to `parallel_agent.py`, delete the script and
its bats suite.

## Parity (verified 2026-05-30)

`parallel_agent.py --help` accepts every flag the skills/docs actually use:
`--json --validate --review --analyze --improve --check-credits --full-output
--timeout`, all `--{claude,gemini,cursor,codex}-model`, `--*-only`, `--no-*`,
`--output`, `--status`. The only `.sh` flag absent from `.py`
(`--include-directories`) is used by **zero** skills/docs. `.py` is a functional
drop-in.

## Decisions (locked)

- **Invocation:** direct — `~/.claude/scripts/parallel_agent.py ARGS` (the file
  is executable with a `#!/usr/bin/env python3` shebang). Closest 1:1 swap to the
  old `.sh` calls; matches how the repo invokes its other scripts directly.
- **Reference breadth:** repoint **all 66** references (incl. `docs/` and
  `docs/templates/`) for a clean cut — no `parallel_agent.sh` string survives.
- **shellcheck:** **keep `-S warning`** (do NOT revert to strict). At default
  severity, 6 other scripts carry ~24 cosmetic findings — 18 of them intentional
  `SC2016` single-quotes in `linear_ops.sh` (literal `$` for `jq`/GraphQL).
  `-S warning` already catches all genuine-defect classes; strict would require
  ~24 suppressions of legitimate code. The policy stands on its own merits, not
  as a workaround for the deleted script.

## Scope of changes

### 1. Repoint references (`.sh` → `.py`, 66 files)

Mechanical path swap, reviewed per context. Reference groups:

- **Live consumers (behavior-affecting):** 17 skill `SKILL.md` files,
  `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `bootstrap.sh`,
  `bootstrap/lib/{deploy,install}.sh`, `configs/claude/config/{command_config,services}.yml`,
  `configs/claude/scripts/check_status.sh`, `configs/cursor/rules/orchestration.mdc`.
- **User-facing guides:** `CLAUDE.md`, `AGENTS.md`, `README.md`,
  `configs/claude/CLAUDE.md`, `configs/gemini/GEMINI.md`,
  `configs/claude/references/{layout,orchestration,parallel-agent}.md`,
  `docs/*.md` (COMMANDS, CONFIGURATION, GETTING_STARTED, TROUBLESHOOTING,
  ARCHITECTURE_DIAGRAMS, PRE_COMMIT, README).
- **Templates / instructional:** `docs/templates/**` (illustrative command
  examples), `tests/test_helper/README.md` — repoint (they read as guidance).

Self-references inside the to-be-deleted files (`parallel_agent.sh` itself,
`tests/bats/parallel_agent.bats`) need no repoint — they are deleted in §2.

#### Historical records — DO NOT repoint (leave factual)

These are dated, point-in-time records of work done *on the `.sh`*; rewriting
them to `.py` would falsify history. They retain their `parallel_agent.sh`
mentions:

- `.Jules/sentinel.md` — security-learnings log (e.g. a 2026-02-06 CWE-377/eval
  finding *in* `parallel_agent.sh`).
- `docs/SHELL_ANALYSIS_REPORT.md` — dated analysis ("Scripts Analyzed:
  bootstrap.sh, parallel_agent.sh", line counts, per-script findings).
- `docs/VALIDATION_REPORT.md` — dated validation report referencing the `.sh`.
- `docs/superpowers/plans/2026-05-30-skillshare-centralized-setup.md` and
  `…-token-economy-and-tiered-claude-md.md` — prior session plans that reference
  the `.sh` as historical context.

This refines the "all 66 / clean cut" decision: **all live + instructional
references are repointed; the handful of historical records above are left as
accurate records.** Literal zero-`.sh`-strings is not the goal where it would
mean falsifying a dated report.

### 2. Delete the deprecated script + its tests

- Delete `configs/claude/scripts/parallel_agent.sh`.
- Delete `tests/bats/parallel_agent.bats` (48 tests of the `.sh` CLI surface).
  `tests/python/test_parallel_agent.py` (54 tests) covers `.py`. No unique
  coverage is ported — the bats suite tested only `.sh` arg parsing, which no
  longer exists.

### 3. CI (`.github/workflows/ci.yml`)

- Remove the `Validate parallel_agent.sh syntax` step (`bash -n
  configs/claude/scripts/parallel_agent.sh`).
- Leave the generic `bash -n configs/claude/scripts/*.sh` loop and the skill/
  script counts unchanged — they adjust automatically (script count drops by 1,
  still ≥ 1).
- Keep `shellcheck -S warning` (per Decisions).

### 4. bootstrap

- `bootstrap/lib/install.sh`: remove the messaging that frames `.sh` as a still-
  working Bash alternative (the "parallel_agent.sh will still work without
  Python" lines); keep the Python-dependency install for `.py`.
- `bootstrap/lib/deploy.sh`: update the `manifest` alias suggestion + the two
  example commands to `.py`; update the `verify_installation` required-file
  check that lists `parallel_agent.sh` → `parallel_agent.py`.
- `bootstrap.sh`: update the line referencing `parallel_agent.sh`.
- `configs/claude/scripts/check_status.sh` + `configs/claude/config/services.yml`:
  update the example/comment to `.py`.

## Out of scope

- Reverting `shellcheck -S warning` to strict (kept by decision).
- Fixing the `.py` itself, adding `--include-directories`, or any `.py` behavior
  change (it is already the maintained drop-in).
- The other deferred follow-ups (`.metadata.json`, pytest `asyncio_mode`).

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| A live consumer used a `.sh`-only flag (`--include-directories`) | Verified: 0 skills/docs use it. Grep confirms before deletion. |
| Direct `.py` invocation fails if `+x` lost or `python3` absent | bootstrap already `chmod +x`s scripts and installs Python (required); `.py` has a shebang. Verified by sandbox e2e. |
| A `parallel_agent.sh` reference is missed | Final `grep -rn parallel_agent.sh .` must return zero hits (success criterion). |
| Deleting `parallel_agent.bats` loses coverage | It only tested the deleted `.sh`; `.py` retains 54 pytest cases. |
| CI structure-count or syntax step breaks on the missing file | Remove the dedicated `.sh` syntax step; the generic loop globs remaining `*.sh`. |
| `deploy.sh` `verify_installation` still asserts `parallel_agent.sh` exists → bootstrap "verify" fails | Update that required-file entry to `.py` (§4). |

## Success Criteria

1. `grep -rn "parallel_agent\.sh" .` (excluding `.git`) returns hits **only** in
   the explicitly-listed historical records (§1); zero in live/instructional
   files.
2. `configs/claude/scripts/parallel_agent.sh` and `tests/bats/parallel_agent.bats`
   are deleted.
3. All live consumers invoke `parallel_agent.py` (skills, CI, pre-commit,
   bootstrap, configs).
4. `bats tests/bats/` passes (without the removed suite); `pytest tests/python/`
   = 54 pass; `shellcheck -S warning …` clean; markdownlint clean on edited
   globbed docs.
5. Sandbox `HOME` bootstrap completes; `verify_installation` passes; the printed
   `manifest` alias + example commands reference `.py`.
6. CI green (Lint, Test, Validate Structure).
