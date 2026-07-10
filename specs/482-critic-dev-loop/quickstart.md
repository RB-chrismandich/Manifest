# Quickstart: Critic-Driven Development Loop (CDDL)

**Feature**: `482-critic-dev-loop` — operator walkthrough for `/spec-implement-loop`.

## Prerequisites

- Manifest bootstrapped (`./bootstrap.sh`) — deploys `~/.claude/scripts/cddl_loop.py`,
  the `cddl` package, and the three role prompts under `~/.claude/prompts/cddl/`.
- An authenticated `claude` CLI (subscription OAuth login is enough; no API key).
- A target repo with a completed feature: speckit (`specs/<NNN-slug>/spec.md` +
  `plan.md`) or superpowers (`docs/superpowers/specs/*-design.md` + paired plan).
- A checked-out **feature branch** (not `main`) with a **clean** working tree.

## 1. Start a run

```bash
# In Claude Code (recommended — the skill mediates clarification Q&A):
/spec-implement-loop specs/123-my-feature

# Or directly:
python3 ~/.claude/scripts/cddl_loop.py start specs/123-my-feature
```

Pre-flight resolves the spec+plan (existing discovery precedence), validates the
three role files, checks git state, and acquires the per-repo lock. Failures exit 6
with one actionable message.

## 2. Answer the clarification gate (phase 1)

If either critic has open questions, the run parks (`exit 3`) and writes them to the
run directory:

```bash
python3 ~/.claude/scripts/cddl_loop.py status         # shows run-id + questions.md path
$EDITOR /tmp/answers.md                               # write your answers
python3 ~/.claude/scripts/cddl_loop.py answer --run <run-id> --answers-file /tmp/answers.md
```

Repeat up to 3 rounds (`--max-rounds`). Both critics must emit a structured
`complete` verdict before any code is produced; exhausted rounds end the run with a
gate-failure report (exit 4) and zero implementation output.

## 3. Watch phase 2 (implementation loop)

Runs unattended within one invocation: implementer produces file-block candidates →
paths are confinement-checked → project gates run (`--verify-cmd`, or auto-detected
bats/pytest/npm/make) → both critics audit independently → deficiencies feed the next
iteration. Bounded by `--max-iterations` (10), per-call timeout (600 s), and run wall
clock (3 600 s).

## 4. Outcomes

| Exit | Meaning | Working tree |
|---|---|---|
| 0 | both critics approved | changes **staged** on your feature branch (staged = approved) |
| 4 | gate failure (open questions) | untouched |
| 5 | ceiling exhausted | last candidate applied, **unstaged**; report lists per-critic deficiencies |
| 7 | aborted (critic/timeout) | applied work left **unstaged** |

The loop never commits, pushes, merges, or reverts your tree.

## 5. Inspect a run

```bash
ls ~/.manifest/cddl/runs/<repo-slug>/<run-id>/
cat .../report.md            # status, blocking critic, outstanding deficiencies,
                             # staged/unstaged disposition, discard instructions
cat .../iterations/2/verdicts.json
```

Runs are kept forever (your call to prune: each run dir is self-contained —
`rm -rf` the run-id dir). Audit trail: `~/.claude/cddl_audit.jsonl` (redacted,
fail-open).

## 6. Tune the roles

Edit `configs/claude/prompts/cddl/{implementer,qa-critic,arch-critic}.md` in the
Manifest repo (prompt body and/or `model:` alias), then `./bootstrap.sh` to redeploy.
Never hand-edit the deployed copies (Configuration-as-Code). Note: a merge-mode
deploy only adds new files (`--ignore-existing`); to propagate *edits* to existing
role prompts, use the replace path / `--reconfigure` — standard `prompts/` semantics.

## Troubleshooting

- **exit 6 "on default branch"** — create/switch to a feature branch first.
- **exit 6 "dirty working tree"** — commit/stash, or rerun with `--allow-dirty`
  (the loop stages only the final approved candidate's paths — never your
  pre-existing edits, never leftovers from rejected iterations; pre-images of
  every file it touches are kept under `iterations/<n>/backup/`).
- **exit 6 "no usable backend"** — `claude` not on PATH or not logged in; run
  `claude /login` or set `CDDL_CLI`.
- **exit 7 after two parse failures** — read the critic's raw output (every
  attempt is persisted): `iterations/<n>/<role>.md` in phase 2, or
  `clarify/round-<n>-<role>.md` in phase 1; usually a role prompt edit broke
  the verdict-block instruction.
