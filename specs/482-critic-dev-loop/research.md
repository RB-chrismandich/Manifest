# Phase 0 Research: Critic-Driven Development Loop (CDDL)

**Feature**: `482-critic-dev-loop` | **Date**: 2026-07-10

All Technical Context unknowns resolved. Each decision records what was chosen, why,
and what was evaluated and rejected. Evidence gathered from a 5-agent parallel recon
over the repository (discovery seam, LLM invocation, state/audit, deploy mechanics,
testing conventions).

## D1 — Language and module layout

- **Decision**: Python 3.11+ package at `configs/claude/scripts/cddl/` with a thin
  entry script `configs/claude/scripts/cddl_loop.py` (shim + `--help` + exit codes).
  Stdlib plus PyYAML (already a repo dependency via `agents/config.py`); no new
  third-party dependencies.
- **Rationale**: A two-phase state machine with JSON persistence, subprocess
  orchestration, and strict parsing is the exact shape of existing Python precedents
  (`parallel_agent.py` → `agents/` package; `smoke_test.py` → `smoke_orchestrator/`).
  The design draft was Python. Ruff targets py311; CI runs pytest on 3.14.
- **Alternatives considered**: Bash (rejected: state persistence + strict JSON verdict
  parsing + path-containment logic is error-prone in shell); extending the `agents/`
  package (rejected: Constitution Principle IV prohibits absorbing new behaviors into
  core scripts when a skill + standalone script suffices, and the spec declares CDDL
  deliberately distinct from the consensus machinery).

## D2 — Artifact discovery (FR-001, FR-002)

- **Decision**: Reuse `spec_review.sh`'s `resolve_artifacts()`/`discover_artifacts()`
  by shelling out from Python to a `bash -c 'source .../spec_review.sh; …;
  resolve_artifacts "$root"'` subprocess, parsing the emitted `role<TAB>path` lines.
  Explicit `--spec/--plan` flags seed the script globals `SPEC`/`PLAN` before the call
  (sourcing skips `parse_args`, so the globals are directly assignable).
- **Rationale**: `configs/claude/references/spec-artifact-discovery.md` ("Reusing the
  shell seam") explicitly blesses sourcing or shelling out to these functions so layout
  rules live in one place; FR-001 forbids a second divergent discovery mechanism.
  Sourcing is safe: `main` is gated by a `BASH_SOURCE` check (spec_review.sh:467).
- **Alternatives considered**: Reimplementing discovery in Python (rejected: FR-001
  violation, guaranteed drift); `check-prerequisites.sh --json --paths-only` (rejected
  as the primary path: speckit-only, no superpowers fallback; spec-review's resolver
  subset is the established dual-workflow precedent).

## D3 — Role definition placement and deployment (FR-013, FR-014)

- **Decision**: Role definitions live at `configs/claude/prompts/cddl/implementer.md`,
  `qa-critic.md`, `arch-critic.md`, using the repo's agent-definition format (YAML
  frontmatter: `name`, `description`, `model` alias, optional `effort`; markdown body =
  role system prompt). They deploy via the existing wholesale `rsync -a` of
  `configs/claude/` (prompts/ is not excluded) — **zero bootstrap changes, no new
  service toggle, no ownership marker**.
- **Rationale**: Recon confirmed `~/.claude/agents/` is Claude Code's user-level
  subagent registry — any `.md` placed there is auto-registered as an invocable
  subagent. CDDL roles are subprocess system prompts, *not* Claude Code subagents, so
  the draft's `configs/claude/agents/` placement would have had an unwanted
  registration side effect and forced a duplicate of feature 481's toggle + marker +
  collision-guard machinery (~10 bootstrap touch points + a bats suite). Under
  `prompts/cddl/` the FR-014 guarantees hold structurally: the deploy rsync has no
  `--delete` (user-added files under `~/.claude/prompts/` survive), the namespace is
  repo-owned (no shared registry to collide in), agents/ and the `.pilotfish` marker
  are untouched (481 guarantees unweakened), and pilotfish name collision is
  impossible by construction.
- **Deploy nuance**: bootstrap's merge mode rsyncs with `--ignore-existing`
  (deploy.sh:126), so on merge-mode machines role-prompt *updates* (not first
  installs) propagate only via the replace path / `--reconfigure` — pre-existing
  semantics for the whole `prompts/` tree, documented in quickstart, not
  CDDL-specific.
- **Spec impact**: SC-008 and the two deploy edge cases were written assuming
  toggle-gated `agents/` deployment; they are amended to the prompts-namespace
  guarantees (no agent registration, redeploy-safe, removable via the deploy-reconcile
  flow). Recorded as a design-correction note in the spec's Clarifications section.
- **Alternatives considered**: Mirror of pilotfish (`agents/` + `--enable-cddl` toggle
  + marker + gate function) — rejected: registers non-subagent prompts as subagents,
  large bootstrap surface for zero user benefit; a new toggle-gated `prompts/` gate —
  rejected: nothing user-owned to protect there, speculative machinery.

## D4 — LLM invocation seam (FR-012)

- **Decision**: Per the `llm-invoke-stdin` skill: invoke
  `[$CDDL_CLI, "-p", "--model", <alias>]` with the full prompt (role body + feature
  context + task) fed via **stdin** (`subprocess.run(..., input=prompt, timeout=...)`),
  argv carrying only fixed flags. Seam = `CDDL_CLI` env var (default `claude`) plus an
  injectable `runner` parameter on the loop core so pytest injects a fake runner and
  bats stubs the binary on PATH. Backend fallback semantics follow the repo convention:
  the authenticated CLI is the default path; no raw API key required.
- **Rationale**: Matches `skillclaw_evolve.py` (`["claude", "-p"]`, input=prompt,
  timeout, injectable runner) and `spec_review.sh` (`printf '%s' "$prompt" | $CLI`).
  ARG_MAX-safe for large spec+plan contexts; offline-testable.
- **Alternatives considered**: Anthropic SDK with `ANTHROPIC_API_KEY` (the draft) —
  rejected: operator machines run OAuth CLI subscription auth (FR-012; clarified
  Claude-only v1); `--append-system-prompt`/`--output-format json` CLI flags —
  rejected: no script in the repo relies on them; instruction content goes in the
  prompt and structure is prompt-enforced with a tolerant-but-strict parser (repo
  convention). The draft's per-role `temperature` settings are dropped — the CLI does
  not expose temperature; role tuning is via prompt + model alias.

## D5 — Verdict integrity (FR-006)

- **Decision**: Critics must end output with a fenced block:
  ` ```cddl-verdict\n{JSON}\n``` `. The parser extracts the **last** such fenced block,
  requires strict `json.loads`, validates `role` matches the invoked role and
  `decision` is in the enum (`approve|reject|questions|complete`); anything else —
  missing block, malformed JSON, wrong role, unknown decision — is non-approval.
  One bounded retry per failed/unparseable invocation, then the run aborts fail-closed.
- **Rationale**: The draft's `"LGTM_QA" in review` substring check is spoofable by
  prose mention (spec edge case "Verdict spoofing"). A fenced JSON block cannot be
  triggered by quoting the token in criticism text, and last-block-wins tolerates
  preamble noise like the repo's existing tolerant parsers (`parse_panel_json`).
- **Alternatives considered**: sentinel substrings (rejected: spoofable, the exact
  FR-006 failure); CLI JSON mode (rejected: unused in repo, less portable across
  CLI versions).

## D6 — Interaction model: re-entrant state machine (FR-003, FR-004)

- **Decision**: The orchestrator is **re-entrant with persisted state**, not a
  blocking interactive process. `cddl_loop.py start <path>` runs pre-flight + one
  clarification round; if open questions remain it writes `questions.md` to the run
  dir and exits with a distinct code (questions-pending). The `/spec-implement-loop`
  skill relays questions to the operator, collects answers, and re-invokes
  `cddl_loop.py answer --run <id> --answers-file <f>` for the next round. Once both
  critics signal complete, phase 2 runs to completion within one invocation (bounded
  by FR-008 timeouts).
  Exit codes: 0 success · 2 usage · 3 questions-pending · 4 gate-failure ·
  5 ceiling-failure · 6 pre-flight failure · 7 aborted (critic/timeout).
- **Rationale**: The draft's `input()` blocks forever under a non-interactive Bash
  tool (how skills execute commands in Claude Code). A re-entrant CLI keeps the
  operator in the loop via the skill while the state machine stays deterministic and
  testable; the persisted-state design also directly satisfies FR-010.
- **Alternatives considered**: blocking `input()` (rejected: incompatible with skill
  execution, untestable); skill-orchestrated per-call scripting with no state file
  (rejected: loses crash diagnosability and makes the state machine's invariants
  unenforceable).

## D7 — Run persistence and audit (FR-010)

- **Decision**: Run directory
  `${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/` (chmod 700),
  `run-id` = UTC timestamp + short suffix. Contents: `state.json` (machine state),
  `questions.md`/`answers-N.md`, `iterations/<n>/` (candidate, verification output,
  raw critic outputs, parsed verdicts), `report.md` (final). Keep-everything — no
  auto-pruning (clarified); self-contained per-run dirs make manual pruning safe.
  Audit events append via the existing `audit_log.sh` (redaction + fail-open) with
  its file env pointed at `~/.claude/cddl_audit.jsonl`.
- **Rationale**: `~/.manifest/<component>/state` is the established home-state
  convention (`lifecycle/state`, `smoke/state`); home placement keeps run artifacts
  out of the target repo's working tree (which the loop must keep clean for git
  safety). `audit_log.sh` is the tested, redacting, fail-open audit writer.
- **Alternatives considered**: repo-local `.manifest/` (the draft) — rejected:
  pollutes the dirty-tree check the loop itself enforces, risks accidental commits;
  `~/.claude/.agent_outputs` — rejected: that namespace is parallel-agent result
  storage with its own consumers (metrics-report).

## D8 — Verification-before-critique gate (FR-009)

- **Decision**: `--verify-cmd '<command>'` per run, with auto-detection defaults when
  omitted: `tests/bats/` → `bats tests/bats/`, `tests/python/` or `pyproject.toml` →
  `pytest`, `package.json` with test script → `npm test -s`, `Makefile` with `test`
  target → `make test`. Multiple detections run in sequence. No gates found → the
  skip is recorded in the iteration record and disclosed in the report (FR-009's
  "where they exist").
- **Rationale**: Deterministic, target-repo-agnostic, and cheap; mirrors
  project-verify's language detection philosophy without coupling to a skill.
- **Alternatives considered**: invoking the `/project-verify` skill (rejected: skills
  are session constructs, not subprocess-invokable contracts); mandatory verify-cmd
  flag (rejected: hostile default for the P1 happy path).

## D9 — Git safety mechanics (FR-011)

- **Decision**: Pre-flight: resolve default branch (`git symbolic-ref
  refs/remotes/origin/HEAD`, fallback `main`/`master` detection) and refuse when
  current branch equals it; refuse when `git status --porcelain` is non-empty unless
  `--allow-dirty`. The loop tracks every path it writes; on success it stages exactly
  the FINAL approved iteration's candidate paths (`git add -- <paths>`) — leftovers
  from earlier rejected iterations stay applied-but-unstaged and are reported with
  discard steps (staged = critic-approved, made literal by the 2026-07-10 technical
  review); on failure/abort everything stays applied and unstaged. It never calls
  commit/push/merge.
- **Rationale**: Explicit-path staging keeps `--allow-dirty` runs from staging
  unrelated edits and enforces the clarified staged-means-approved semantic.
- **Alternatives considered**: `git add -A` on success (rejected: stages pre-existing
  dirt under `--allow-dirty`); auto-revert on failure (rejected in clarification Q1).

## D10 — Write confinement (FR-017)

- **Decision**: The implementer must emit candidates as structured file blocks
  (path + full file content, contract-defined grammar). Before any write, each path is
  validated: must be relative, no `..` segments, and `realpath` of the resolved parent
  directory must remain inside `realpath(repo_root)` (catches symlink escapes).
  Any violation rejects the entire candidate pre-write and records a confinement
  deficiency fed back per FR-007.
- **Rationale**: Whole-candidate rejection keeps iterations atomic (no partial
  writes); parent-realpath containment is the `llm-audit-traversal` guidance for
  LLM-named paths.
- **Alternatives considered**: unified-diff candidate format (rejected for v1: apply
  failure modes — context drift, fuzzy offsets — add a failure axis unrelated to the
  feature's value; full-file blocks are what the draft's coder produced); per-file
  skip-and-continue on violation (rejected: partial candidates make verdicts
  ambiguous).

## D11 — Timeout enforcement (FR-008)

- **Decision**: Per-invocation: `subprocess.run(..., timeout=CDDL_INVOKE_TIMEOUT)`
  (default 600 s), `TimeoutExpired` → failed call, one retry, then abort (exit 7).
  Whole-run: monotonic deadline (`CDDL_RUN_TIMEOUT`, default 3600 s) checked before
  each step; each invocation's timeout is additionally capped by remaining run budget.
- **Rationale**: Matches `skillclaw_evolve.py` subprocess-timeout precedent; the
  remaining-budget cap prevents the last invocation from overshooting the wall clock.
- **Alternatives considered**: `timeout(1)`/`gtimeout` wrappers (rejected: Python
  owns the subprocess; platform.sh helpers are a bootstrap-only convention).

## D12 — Skill and registration (FR-015, FR-016)

- **Decision**: Skill `spec-implement-loop` in `.skillshare/skills/spec-implement-loop/SKILL.md`
  (domain `spec`, verb `implement`, qualifier `loop` — taxonomy-compliant; dual-workflow
  `spec-` prefix per the c343a34 rename precedent). `command_config.yml` `tool_policies`
  entry: allowed `[Bash, Read]`, `parallel_agents: never`, `validation_tier: 1`,
  `subagents: never` with rationale (the loop is its own sequential role machine).
  Regeneration chain on skill add: cursor `.mdc` via `generate_cursor_rules.sh`,
  `docs/COMMANDS.md` + GEMINI/AGENTS guide injections via
  `generate_commands_doc.py --inject-guides`, skill-count strings. Frontmatter must fit
  the 22 000-byte aggregate budget (current headroom ≈ 834 bytes → description ≤ ~290
  chars), measured at deployed size. `cddl_loop.py` ships `--help` (≤15 lines, exit 0)
  and an `err()` stderr helper per script conventions (specs/003 R6/R7).
- **Alternatives considered**: name `spec-loop-dev` (rejected: verb must be second
  token); `speckit-loop-dev` + project-local skills-dir placement (rejected in spec
  Assumptions: dual-workflow skills use `spec-`, source of truth is `.skillshare/`).

## D13 — Test strategy (Constitution VI Verify gate)

- **Decision**: pytest package tests at `tests/python/cddl/` (fake runner injected
  through the D4 seam; covers state machine, verdict parser incl. spoof fixtures,
  confinement incl. symlink escape, git preflight via tmp repos). Bats CLI tests at
  `tests/bats/cddl_loop.bats` (PATH-stubbed `claude` per `git_ops.bats` mock-bin
  pattern; covers `--help`, exit codes, discovery integration on fixture layouts).
  Smoke: one Lite-tier entry appended to `smoke-catalog/manifest.yaml` via
  `smoke_test.py append` — hermetic mktemp fixture repo + stub CLI that approves on
  iteration 1; asserts exit 0, staged file present, report exists (the Verify gate's
  critical-path smoke for the new user-facing workflow).
- **Rationale**: Mirrors the repo's three-layer convention exactly; every FR-006/
  FR-017 negative case is cheap to fixture through the injectable runner.

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Language/runtime | Python 3.11+ stdlib + PyYAML (D1) |
| Discovery reuse | source spec_review.sh seam via bash subprocess (D2) |
| Role file location/deploy | `configs/claude/prompts/cddl/`, zero-touch rsync (D3) |
| Model access | `claude -p --model <alias>` via stdin, `CDDL_CLI` seam (D4) |
| Verdict format | fenced `cddl-verdict` JSON block, fail-closed (D5) |
| Operator interaction | re-entrant CLI, exit-code contract, skill mediates (D6) |
| Run state location | `~/.manifest/cddl/runs/…`, audit via audit_log.sh (D7) |
| Verify gate | `--verify-cmd` + auto-detect, disclosed skip (D8) |
| Git mechanics | preflight checks, explicit-path staging (D9) |
| Confinement | file-block grammar + parent-realpath containment (D10) |
| Timeouts | subprocess timeout + monotonic run deadline (D11) |
| Skill name/registration | `spec-implement-loop`, tool_policies, regen chain (D12) |
| Tests/smoke | pytest + bats + Lite smoke entry (D13) |
