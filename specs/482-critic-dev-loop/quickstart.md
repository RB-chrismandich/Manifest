# Quickstart: Critic-Driven Development Loop (CDDL)

**Feature**: `482-critic-dev-loop` — operator walkthrough for `/spec-implement-loop`.

## Prerequisites

- Manifest bootstrapped (`./bootstrap.sh`) — deploys role prompts under
  `~/.claude/prompts/cddl/` (used by sub-agent dispatches).
- A target repo with a completed feature: speckit (`specs/<NNN-slug>/spec.md` +
  `plan.md`) or superpowers (`docs/superpowers/specs/*-design.md` + paired plan).
- A checked-out **feature branch** (not `main`) with a **clean** working tree.
- An agent session with **Task** sub-agent support (Cursor Agent, Claude Code, etc.).

## Run CDDL (sub-agent orchestration)

```bash
/spec-implement-loop specs/123-my-feature
```

The skill:

1. Resolves spec + plan (speckit or superpowers discovery).
2. Runs a **clarification gate** — developer-reviewer, QA critic, and architecture
   critic may ask questions; you answer in chat until all three emit `complete`.
3. Enters the **implementation loop** — only the **developer** sub-agent writes code;
   the three reviewers audit each candidate until all approve with zero findings.
4. Stages approved changes on your feature branch (never commits or pushes).

The scripted `cddl_loop.py` / `manifest cddl` CLI was retired; orchestration lives
entirely in the skill and its sub-agent dispatches.

## Tune the roles

Edit `configs/claude/prompts/cddl/{developer,developer-reviewer,qa-critic,arch-critic}.md`
in the Manifest repo (prompt body and/or `model:` alias), then `./bootstrap.sh` to
redeploy. Never hand-edit deployed copies (Configuration-as-Code). To propagate
*edits* to existing role prompts, use `--reconfigure` — standard `prompts/` semantics.

## Troubleshooting

- **Pre-flight: default branch** — create/switch to a feature branch first.
- **Pre-flight: dirty tree** — commit/stash before starting.
- **Reviewer parse failures** — read the sub-agent output; usually a role prompt edit
  broke the `cddl-verdict` fenced-block instruction (see
  `configs/claude/prompts/cddl/verdict-format.md`).
- **Ceiling / stall** — increase iteration budget in the skill invocation or narrow
  scope; inspect staged vs unstaged files before continuing.
