# Proposed skill changes (from the eval suite)

Filed from the eval run of 2026-09-27 (`--runs 3`, sonnet agent, opus judge). The
plugin was treated as read-only while the suite was built; apply these as a separate
change, then re-run the named skills' evals and compare Δ against the numbers below.

| Skill | Δ (full run) | Action |
|---|---|---|
| token-benchmark | +0.83 (01–02, runs 3) | Move out of the bundle |
| token-conserve | −0.02 (all 6 cases, runs 3) | Slim + user-invoked |
| test-isolate-ambient | +0.03 | Rewrite as a concrete checklist |
| memory-compress | −0.05 | Shrink to the non-obvious rules |

## token-benchmark — move to a repo-local skill

Monorepo-only by its own SKILL.md: the installed bundle does not ship the benchmark
runtime, so for plugin users the skill can only explain that it can't run. Its high Δ
measures that honesty, not a working feature.

- Move `skills/token-benchmark/` to the repo's `.claude/skills/` (project-scoped, like
  the speckit skills); remove it from the bundle manifest and `plugin.json`.
- Delete `evals/token-benchmark/` in the same change.
- Run the skill-lifecycle generators (`docs/COMMANDS.md`, guide index, Cursor rules).

## token-conserve — slim, user-invoked, "terse, not silent"

Δ −0.02 at runs 3 (with-plugin was *less* terse than baseline on -01 and -04; tied on
-03 and -06): a plain "be terse" request does as well, and the always-on `token-economy`
SessionStart hook already injects the baseline. Its unique jobs are an explicit
`/token-conserve` re-assert (named in the global CLAUDE.md) and the Devin delivery path.

- Cut to ~15 lines: Output, Edits, Before coding, Context rules only.
- Add: "Terse, not silent — state any default or assumption you chose, and anything
  not done." (fixes the bare "Done." regression in token-conserve-03).
- Add `disable-model-invocation: true` so it fires on `/token-conserve` only.
- Move the ~25-line "Persistence caveat" (per-harness delivery paths) to the bundle
  README; it is maintainer documentation loaded on every invocation.
- Evals: token-conserve-03 (states defaults) and -06 (re-assert after a verbose answer)
  are the ones that should move.

## test-isolate-ambient — concrete checklist

Both arms fail the same concrete points; the 19-line skill is too generic to change
behavior. Replace the prose with a checklist:

- HOME and every XDG root redirected to a tmp fixture (or `Path.home` patched).
- git: `GIT_CONFIG_GLOBAL` → fixture, `GIT_CONFIG_NOSYSTEM=1`, run outside any repo.
- Network/CLIs: stub binaries first on `PATH`; `UV_NO_NETWORK=1`.
- Catch only the specific missing-state error (`FileNotFoundError`); malformed input and
  other I/O errors must stay visible — test both.
- Run the new test red against the unfixed code before the fix, then green.

If Δ is still ≈ 0 after this, remove the skill.

## memory-compress — shrink to what's non-obvious

The baseline already compresses and merges well (Δ −0.05, within noise on 6 cases).

- Keep: never invent IDs/facts (say what's missing), the provenance gate, SKIP sentinel,
  copy the pre-computed header verbatim **on its own line** (both arms put entry text on
  the header line in memory-compress-04 — add an explicit example).
- Cut: generic compression advice (articles, shorthand lists, "fair game to drop").

If Δ stays ≈ 0 after shrinking, consider folding the provenance rules into
`session-checkpoint` / learning-capture docs and retiring the skill.

## Defect fixes (keep the skill)

See README "Known plugin issues" for ai-hooks-integration, deploy-reconcile, pr-smoke,
pass-cli, prompt-optimize, session-checkpoint and skill-evolve.
