# manifest-workspace evals

One folder per skill (`evals/<skill>/<skill>-NN-slug/`), 5–6 cases each:
≥4 should-fire cases across distinct input shapes, ≥1 should-NOT-fire near-miss.
Case names are the leaf directory names, so `--case '<skill>-*'` selects one skill.

## Run

Run from the Manifest repo root; the target must be the plugin root (targeting
`evals/` itself loads no plugin and collapses the Δ to baseline-only).

```bash
# full suite (headline number = Δ, with-plugin score minus without-plugin score)
claude plugin eval plugins/manifest-workspace --ablation with-without \
  --model sonnet --judge-model opus --allow-tools Bash Write Edit -j 8 --no-publish

# one skill
claude plugin eval plugins/manifest-workspace --ablation with-without \
  --case 'memory-compress-*' --model sonnet --judge-model opus \
  --allow-tools Bash Write Edit --no-publish
```

Operator requirements: `python3`, `git`; for meaningful pr-smoke results also a working
`pytest` and `shellcheck` on `PATH` (missing tools make the runner report WARN, which the
pr-smoke rubrics accept). Test-writing cases accept pytest or stdlib `unittest`.

- `--allow-tools Bash Write Edit` is required: no skill declares `allowed-tools`, and
  cases that build fixtures (receipts, repos, stores) or produce files need them.
  Each case's `allowed_tools` still narrows what it may use (pass-cli cases get no Bash,
  because a real `pass-cli` may be installed and authenticated on the operator's machine).
- Judge is opus, agent is sonnet (judge must not be the agent model).
- `runs: 3` per case; do not lower.

## Conventions

- Receipt/state skills point `XDG_STATE_HOME` / `XDG_DATA_HOME` at `./state` / `./data`
  in the sandbox cwd and write fixtures there, so results never depend on the operator's
  real install.
- Every case has ≥1 outcome grader. `tool_used: Skill` graders are display-only
  trigger checks (excluded from score under ablation). Spec-literal keyword regexes
  (e.g. `degraded`) are weight 0.5 secondaries.
- For skills that write memory/state after answering (automation-rework-breakeven),
  llm graders judge the full trace, because the final message can be a short coda.
- session-checkpoint `runtime-checkpoint` / `revalidates` item 4 require the skill's
  `session_continuity.py` checkpoint/verify runtime (integrity envelope, private perms),
  which the no-plugin arm cannot know — they are weight 1 and inflate Δ somewhat by
  design; the outcome rubrics (payload honesty, ownership, secrets) carry weight 2.

## Sandbox caveats (found while piloting)

- The eval sandbox denies writes to any `.git/config` (on every OS), so git-using cases
  keep repo metadata in `./gitmeta` via `GIT_DIR`/`GIT_WORK_TREE` exported in a
  per-command prefix, and `git init --template=` (template hook copy is read-denied).
- On macOS the xcrun `/usr/bin/git` shim fails in the sandbox, and `stat` on the
  Command Line Tools dir is denied — so both `[ -d … ]` guards and PATH lookup of a bare
  `git` in that dir silently fall through to the blocked shim; only exec by full path
  works. The prefix therefore probes by exec (`"$G" --version`) and, if that succeeds,
  writes a `./.gitbin/git` wrapper that `exec`s the full path and puts `./.gitbin` first
  on `PATH`, so bare `git` (including inside the pr-smoke runner) works. No-op elsewhere.
- If a run still reports "no usable git" and scores 0 in both arms, treat it as an
  infrastructure miss, not a plugin result; Linux/CI avoids the xcrun issue entirely.
- The harness's native config dir (`<sandbox>/config`) is read-denied, so config-audit /
  deploy-reconcile can never inspect real native inventories here; their cases grade
  receipt-level verdicts and honest DEGRADED reporting.
- On the pilot machine `pytest` was broken (missing `pygments`), which skews pr-smoke /
  test-isolate-ambient runs that shell out to pytest.

## Known plugin issues the suite surfaces (file as follow-ups; plugin not edited)

- `pr-smoke`: full mode FAILs on any non-Manifest repo — it hard-codes
  `tests/lint/check_array_expansion.sh` / `check_bats_assertions.sh`, and did not run
  the repo's pytest in a probe. Cases pr-smoke-01/02 grade the user-visible outcome.
- `session-checkpoint`: SKILL.md says to fill the markdown `summary-template.md`, but
  `session_continuity.py checkpoint` requires a 12-field JSON payload. In one pilot the
  agent passed a pasted secret verbatim into the Skill tool's args while telling the user
  it was not copied into the checkpoint (-01).
- Plugin-root `CLAUDE.md` is context-mode routing guidance that mandates `ctx_*`
  tools the plugin does not ship.
- `help`: catalog search is substring-only; multi-word queries ("stale branches")
  return no match.
- `pr-smoke`: the runner only runs pytest under `tests/python/`, so a repo's own
  `tests/` suite is silently skipped (pr-smoke-01).
- `deploy-reconcile`: `plugin_reconcile.py` compares the receipt only against a
  hard-coded bundle list, never harness-native inventories (contrary to SKILL.md), so the
  skill reports "in sync — no repair required" on receipt evidence alone
  (deploy-reconcile-02/03). It also reversed drift direction in one pilot (-05).
- `ai-hooks-integration`: the CLI-wrapper template swallows the hook's exit code
  (`|| true`), so gating `gh pr create` on an audit script needs an adapter the skill
  doesn't provide (-03); no guidance on redacting secrets or opening a shared-dir log
  safely (-05). Its bundled OpenCode reference documents only the exported-function
  plugin API; if OpenCode's newer `Plugin.define` API is current, the reference may be
  stale (ai-hooks-integration-05 is pinned to the documented API for that reason).
- `pass-cli`: invited pasting the retrieved password back into chat in one pilot (-01).
- `token-conserve`: over-terse — replied only "Done." without stating the defaults it
  chose for an ambiguous request (-03).
- `prompt-optimize`: sometimes emits a "Here's…" preamble despite "template only" (-01).
- `skill-evolve`: told the user SkillClaw doesn't exist (-04); re-asks for authorization
  the user already gave, prompted by `--apply`'s "requires … authorization" reason text (-02).
- `pass-cli`: when handed a PAT in chat, refused storage but didn't tell the user to rotate
  the exposed token, and offered to return the API key in chat (-02).

## Unsure graders (watch in full runs)

- config-audit-02/03: judges split on defensible DEGRADED/classification answers.
- prompt-optimize-03: strict on per-reviewer payload specification.
- token-benchmark-02: flaky when the agent discovers the real checkout above the sandbox.
- `tool_used: Write` caps (1–2 fixture writes) fail an agent that rewrites a fixture.
- config-audit-03's receipt `capabilities` shape is invented (no receipt schema ships).
- session-checkpoint-01 `no-secret-anywhere`: the judge call was once blocked by the
  judge model's safety filter while reading the trace (grader error, not an agent
  failure) — rerun or check that grader by hand when it errors.
- token-benchmark-02 was flaky only under the old assumption-based rubric; now graded on
  runtime evidence.
