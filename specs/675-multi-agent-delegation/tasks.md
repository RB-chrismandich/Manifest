# Tasks: Multi-Agent Delegation Plugin

**Input**: Design documents from `/specs/675-multi-agent-delegation/`

**Prerequisites**: plan.md, spec.md, research.md (D1–D11 settled — do not reopen),
data-model.md, contracts/ (4 files), quickstart.md

**Tests**: Included — plan.md's Testing section and Constitution Principle VI
mandate them: pytest dispatcher/job suites, bats registration + hook-wiring
gates, SC-004 fault-injection matrix, and one smoke-catalog entry per shipped
user-facing workflow (delegate, readiness, second-opinion, review, gate).
Write each phase's failing tests before that phase's implementation.

**Organization**: Grouped by user story (US1–US4 from spec.md) plus a parity
phase for the standalone review surface (SC-002 rows 3–4, prescribed by
plan.md's Phase 2 ordering between US3 and US4).

**Hard constraints carried into tasks** (measured 2026-08-05, handoff +
plan.md): cross-skill warning-ref ratchet **133/133 — zero headroom**: new
SKILL.md bodies contain zero prose cross-skill references (file-path links
only); catalog frontmatter 25110/29000 (two ~250-char descriptions fit);
plugin.json needs an EXPLICIT `skills` array; `expected_total` 114 → 116;
dispatcher is stdlib-only (registry is `backends.json`, JSON not YAML); first
plugin `hooks/` in the repo needs a new bats wiring gate; no model IDs in
SKILL.md/agent frontmatter (tiers by name); implementation PR carries the
`manifest parallel-agent` Tier-1 gate; sub-agents pin Sonnet.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 for user-story phases only
- Every task names exact file paths

## Path Conventions

Monorepo plugin bundle: `plugins/manifest-delegate/` + registration surfaces at
repo root / `configs/claude/config/` + `tests/{python,bats}/` +
`smoke-catalog/manifest.yaml` (per plan.md Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Plugin skeleton + manifest so every later task has a home.

- [x] T001 Create the bundle skeleton `plugins/manifest-delegate/` with
      subdirs `.claude-plugin/`, `config/`, `scripts/`, `hooks/`, `agents/`,
      `skills/delegate/references/`, `skills/delegate-setup/`
      (plan.md Project Structure; read
      `~/.claude/references/code-constitution.md` before any source file)
- [x] T002 Author `plugins/manifest-delegate/.claude-plugin/plugin.json` with
      name `manifest-delegate`, version `0.1.0`, description, and an EXPLICIT
      `skills` array listing `./skills/delegate` and `./skills/delegate-setup`
      — no auto-discovery (repo rule; baseline's discovery-based plugin.json is
      deliberately not mirrored, research.md baseline notes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Registry, config resolution, job store, and envelope — every user
story routes through these. **No user-story work before this phase completes.**

- [x] T003 [P] Author the backend registry
      `plugins/manifest-delegate/config/backends.json` conforming to
      `specs/675-multi-agent-delegation/contracts/backend-registry.schema.json`:
      exactly `codex`, `claude`, `antigravity` (alias `agy`); per entry:
      invoke/resume argv templates + `model_args` + `tier_source` +
      `default_tier` (codex `auto`, claude `sonnet`, antigravity `flash`),
      `session_id_capture`, `input` (transport `stdin`/`temp_file`/`argv` +
      `max_payload_bytes` + `max_context_bytes` — large prompts never via
      argv), readiness (`version_cmd`, `auth_probe_cmd` ≤10s,
      `install_fix`, `login_fix`; `retired_check`: `null` for all three
      shipped entries (no known retired predecessor) — the `retired` state
      stays reachable via fixtures (T018) and future registry entries),
      sandbox `read_only_args`/`write_args` per
      the D8 security profiles (codex `--sandbox read-only|workspace-write`;
      claude sandbox-enabled `--settings` + read-only `--permission-mode
      plan` + `--disallowedTools` denylist — a denylist alone leaves Bash as
      a mutation path — with write swapping to `--permission-mode
      acceptEdits`; agy `--sandbox --mode plan` read-only / `--sandbox
      --mode accept-edits` write — sandbox + explicit mode in BOTH modes;
      schema `safeArg` pattern makes `dangerously|bypass` tokens
      unrepresentable), `prompting_ref`,
      `services_key`, `transfer` (codex: `{"method":"app_server_import"}`;
      claude/antigravity: `null` — transfer support is registry-declared,
      never name-branched); seed facts from research.md D4 invocation table
      (codex invoke carries `--json` + `--output-last-message`; its
      `session_id_capture` = `jsonl_event` on the version-gated
      `thread.started` event). Acceptance: resolve the claude auth probe
      concretely before seeding — verify the chosen `auth_probe_cmd` against
      a real authenticated AND logged-out claude CLI (non-interactive, ≤10s,
      negligible token spend), record the final command in research.md D4;
      confirm each CLI's stdin prompt invocation against the real binary
      (`codex exec -`, `claude -p` with no prompt arg, agy) before seeding
      `input.transport`, record results in research.md D4; record the
      derivation of each `input` limit — `max_payload_bytes` from a measured
      ARG_MAX-safe transport bound, `max_context_bytes` from the backend's
      documented context window or explicit `null` with rationale — no
      invented numbers
- [x] T004 Scaffold `plugins/manifest-delegate/scripts/delegate.py`:
      stdlib-only argparse dispatcher with subcommand stubs
      `task|review|status|result|cancel|setup|transfer|gate|resume-candidate`
      plus the hidden internal worker mode (background supervisor, excluded
      from `--help` text); early interpreter probe as the first executable
      statements (2.7-parseable prologue, exits 2 with the exact ≥3.9
      remediation from research.md D11, before even `--help`); syntax floor
      Python 3.9 (no match/case, no runtime PEP 604 unions);
      `--help` on bare invocation and every subcommand (≤15 lines, exit 0,
      before any config/state lookup — `tests/bats/help_coverage.bats`
      auto-enumerates it); `--json` plumbing; exit-code contract 0/1/2/3;
      spawn helper using argv arrays only, own process group, `stdin=DEVNULL`
      except stdin-transport prompt delivery (payload then EOF; large prompts
      never via argv — 0600 temp file `{prompt_file}` otherwise)
      (contracts/delegate-cli.md Global rules)
- [x] T005 [P] Write failing config/registry unit tests in
      `tests/python/test_delegate_dispatcher.py`: registry validation (unique
      ids/aliases, no shell metacharacters in templates; a fixture registry
      containing a `dangerously|bypass` token is refused at dispatcher load
      with exit 2 — runtime re-validation, D8); version probe: a simulated
      pre-3.9 interpreter (monkeypatched `sys.version_info`) exits 2 with
      the D11 remediation message verbatim; `delegation.json`
      parses always; `delegation.yml` honored only when PyYAML importable,
      else stderr report + factory defaults (FR-013); `.json` wins when both
      exist; resolution explicit > `$MANIFEST_CONFIG_DIR` > `~/.claude/config/`;
      workspace `services.yml enabled: false` beats user enable with layer
      attribution; tier passthrough when `model_tiers` absent;
      `MANIFEST_DELEGATIONS_DIR` override honored; FR-016 extensibility: a
      synthetic fourth backend in a fixture registry is honored by the
      resolution/readiness surfaces with zero backend-name branching in
      `delegate.py`
- [x] T006 Implement config loading in
      `plugins/manifest-delegate/scripts/delegate.py`: compiled factory
      defaults (codex default, all enabled, 600s budgets, gate off);
      `delegation.{json,yml}` per research.md D3 report-and-proceed error
      policy (deliberate divergence from agents-config `ConfigError`);
      `services.yml` enable flags via fixed-format line reader matched to
      `write_services_config()` in `bootstrap/lib/config.sh` (never requires
      PyYAML); `parallel_agent.yml` `model_tiers` consulted only when PyYAML
      importable
- [x] T007 Implement the job-record store in
      `plugins/manifest-delegate/scripts/delegate.py`: per-job dirs
      `~/.claude/.agent_outputs/delegations/<ws-slug>-<sha256(cwd)[:16]>/<job-id>/`
      with `record.json`/`output.txt`/`job.log` (data-model.md field list);
      state machine `queued→running→{completed,failed,timeout}` +
      `queued|running→cancelled`, terminal states immutable; every
      `record.json` mutation is compare-and-replace inside a per-job
      `fcntl.flock` critical section (`<job-dir>/.lock`: acquire → re-read →
      refuse if terminal → temp file + atomic rename → release; no
      re-read/rename TOCTOU window — first terminal write wins);
      worker/pgid liveness check on read with reaper: dead worker +
      non-terminal ⇒ kill the recorded backend pgid if still alive, then
      `failed` "process died without result";
      keep-last-50 prune on write; `MANIFEST_DELEGATIONS_DIR` env override
- [x] T008 Implement result-envelope normalization in
      `plugins/manifest-delegate/scripts/delegate.py` per
      `specs/675-multi-agent-delegation/contracts/result-envelope.schema.json`:
      mechanical extraction per the schema's contract — take the LAST fenced
      JSON block from captured output, validate required fields with stdlib
      `json`, never derive fields from prose; backend/model attribution,
      outcome success|partial|failure; empty/malformed/no-block output ⇒
      `failure` + "backend returned nothing usable" with raw output
      preserved — never fabricate a summary (SC-004)

**Checkpoint**: dispatcher parses config + registry, stores job records,
normalizes envelopes — user stories can begin.

---

## Phase 3: User Story 1 — Delegate a task to a chosen agent backend (P1) 🎯 MVP

**Goal**: Uniform delegation to codex/claude/antigravity with background job
management, resume/follow-up, and transfer — the baseline's core generalized.

**Independent Test**: Delegate one small task three times (once per backend,
mocked CLIs in tests); each ready backend returns the same envelope shape; an
unready backend returns cause + remediation + ready alternatives (US1 AS1–AS5).

- [x] T009 [P] [US1] Write failing job-lifecycle tests in
      `tests/python/test_delegate_jobs.py` using stub backend CLIs on PATH:
      foreground completion; background spawn → status → result → cancel;
      launcher-exit: a background job reaches its terminal state with a
      complete envelope after the launcher process has exited (detached
      worker survives); worker-crash: SIGKILL the worker mid-run ⇒ a status
      read reports `failed` "process died without result" AND the backend
      process group is confirmed dead after that read (reaper);
      timeout: the worker kills the process group and records `timeout` +
      partial state;
      two concurrent jobs write disjoint dirs (no interleave); keep-last-50;
      cancel on a non-terminal job (even with a dead process) CAS-transitions
      it to `cancelled`; cancel on a terminal job is a reported no-op leaving
      the record unchanged; a simulated completion/cancel race serializes
      through the per-job lock and leaves exactly
      one terminal state (first write wins);
      envelope-extraction fixtures: stub output ending in a valid fenced
      JSON envelope parses into the record; stub output with no valid block
      ⇒ failure envelope with raw output preserved;
      `session_id_capture` populated in `record.json` after a run — codex
      `jsonl_event` parsing validated against fixtures captured from real
      `codex exec --json` JSONL under `tests/python/fixtures/codex/` (one
      with `thread.started`, one older-CLI sample without ⇒ `session_ref`
      null + resume-unavailable disclosure);
      input-transport boundaries: a prompt above `max_payload_bytes` on an
      argv-transport fixture backend is rejected naming the transport limit;
      a stdin-transport stub receives a large prompt intact (stub echoes
      byte count); a prompt above a fixture `max_context_bytes` is rejected
      naming the model-context limit;
      `--resume`/`--resume-last`/`--fresh` route through the registry resume
      template; `resume: null` backend discloses and re-sends context
      (FR-015); `resume-candidate --json` shape; transfer: `--source`
      path-traversal guard (must canonicalize — realpath, symlinks resolved —
      to a path under `~/.claude/projects/` or `~/.claude/transcripts/`;
      traversal/symlink escapes rejected) and the
      claude/agy no-import fallback offers `task` with re-sent context;
      spawn-overhead timing: wall-clock minus stub-backend runtime < 2s
      (plan.md performance goal)
- [x] T010 [US1] Implement `task` foreground path in
      `plugins/manifest-delegate/scripts/delegate.py`: backend resolution via
      registry ids/aliases (unknown ⇒ exit 2 + known-backend list; unavailable
      ⇒ exit 3 + cause + remediation + ready alternatives, never silent
      fallback, FR-004); sandbox mapping read-only default / `--write`
      sandbox-scoped only (read-only: codex `--sandbox read-only`, claude
      `--permission-mode plan` + denylist, agy `--sandbox --mode plan`;
      write: codex `--sandbox workspace-write`, claude sandbox-enabled
      `--settings` + `--permission-mode acceptEdits`, agy
      `--sandbox --mode accept-edits` — sandbox retained, D8); model
      tier + budget resolution (per-invocation > per-backend > 600); compose
      prompt injecting the envelope contract (D10); prompt delivery per
      registry `input.transport` (stdin payload / 0600 temp file
      `{prompt_file}` — never argv for large prompts); context-size
      validation against BOTH `input.max_payload_bytes` (transport) and
      `input.max_context_bytes` (model context) — exceeding either ⇒
      explicit error naming the specific limit, never silent truncation
      (data-model.md Delegation Request
      validation; spec edge case); always state the chosen backend (US1-AS4)
- [x] T011 [US1] Implement `--background` mode plus `status`/`result`/`cancel`
      subcommands in `plugins/manifest-delegate/scripts/delegate.py` per
      contracts/delegate-cli.md: `--background` spawns the detached worker
      supervisor (owns budget timeout + process-group kill, atomic envelope
      write, sets terminal state exactly once) and prints `job_id` +
      check-command; status table / detail / `--wait --timeout` with
      worker/pgid dead-process detection; result prints envelope +
      `raw_output_path`, active ⇒ exit 1; prefix
      matching with ambiguity ⇒ exit 2; cancel = pgid kill + CAS cancellation
      of non-terminal records only, terminal ⇒ reported no-op (FR-014)
- [x] T012 [US1] Implement resume/follow-up in
      `plugins/manifest-delegate/scripts/delegate.py`: `session_id_capture`
      per registry entry on every run (incl. `jsonl_event`: scan codex
      `--json` stdout JSONL for `thread.started` → thread id; event absent ⇒
      `session_ref` null + disclosure, never an error);
      `--resume <job-id>`/`--resume-last`/
      `--fresh` replay through the registry `resume` template; `resume: null`
      backends ⇒ disclosed + context re-sent fresh (FR-015); implement
      `resume-candidate --json` reporting
      `{available, job_id, backend, session_ref, age}`
- [x] T013 [US1] Implement `transfer` in
      `plugins/manifest-delegate/scripts/delegate.py`: backends whose
      registry `transfer.method` is `app_server_import` (shipped: codex) —
      short-lived direct `codex app-server` external-session-import call
      returning thread id + resume command (D1); backends with `transfer:
      null` (shipped: claude/agy) — state no import support and offer `task`
      with re-sent context (registry-driven, FR-016: no backend-name
      branching); `--source` defaults to the
      SessionStart-captured transcript and must canonicalize (realpath) to a
      path under `~/.claude/projects/` or `~/.claude/transcripts/`
      (path-traversal guard — covers both harness transcript roots)
- [x] T014 [P] [US1] Author the four reference files under
      `plugins/manifest-delegate/skills/delegate/references/`:
      `result-envelope.md` (FR-002 presentation rules),
      `prompting-codex.md`, `prompting-claude.md`, `prompting-agy.md` —
      ORIGINAL guidance per research.md D10; do not vendor baseline text
      (licensing note, D5); baseline at
      `~/.claude/plugins/cache/openai-codex/codex/1.0.6/` is parity reference
      only; each reference must cover the baseline guidance's topic set —
      output contract, constraint framing, style/effort conventions —
      recorded as a checklist comment at the top of each file (the FR-007
      "matching quality" proxy)
- [x] T015 [US1] Author `plugins/manifest-delegate/skills/delegate/SKILL.md`:
      delegation + follow-up + job verbs + transfer entry point, backend as
      parameter, read-only default + `--write` scope statement; body instructs
      loading the matching `references/prompting-<backend>.md` before
      composing a delegation prompt (FR-007 per D10 — the dispatcher injects
      only the envelope contract); description
      ≈250 chars (catalog frontmatter 25110/29000); body contains ZERO prose
      cross-skill references (ratchet 133/133 — file-path links only) and no
      model IDs (tiers by name, `configs/claude/references/harness-routing.md`)
- [x] T016 [P] [US1] Author `plugins/manifest-delegate/agents/delegate-runner.md`:
      thin forwarder — `model: sonnet` (tier name), `tools: Bash`; contract:
      one dispatcher call, stdout verbatim, no independent solving (baseline
      `codex-rescue` non-autonomy generalized, research.md D6)
- [x] T017 [US1] Append delegate-workflow smoke entries (tier Lite, type cli,
      hermetic fixture home, stub backend CLI, expect_exit 0) to
      `smoke-catalog/manifest.yaml` via
      `configs/claude/scripts/smoke_test.py`: one foreground delegate, one
      background status→result→cancel chain (Constitution VI; restore the
      catalog header comment if append strips it)

**Checkpoint**: US1 fully functional and independently testable — MVP.

---

## Phase 4: User Story 2 — Verify backend readiness (P2)

**Goal**: One non-interactive check reporting installed/authenticated/ready +
exact remediation for all registry backends in <30s.

**Independent Test**: Run readiness with one backend ready and one not (stubs);
the report distinguishes states and gives an actionable fix (US2 AS1–AS3).

- [x] T018 [P] [US2] Write failing readiness tests in
      `tests/python/test_delegate_dispatcher.py`: probes run in parallel with
      per-probe ≤10s timeout; states `ready|not_installed|not_authenticated|
      disabled_workspace|disabled_user|retired|error` each reachable via
      fixtures; remediation strings come verbatim from the registry entry;
      blocking config layer named (workspace vs user, FR-013); never prompts
      for input; when the auth probe output carries an account/login
      identity, the readiness row's `identity` field is populated (fixture
      asserts it); absent ⇒ null
- [x] T019 [US2] Implement `setup` readiness mode in
      `plugins/manifest-delegate/scripts/delegate.py`: parallel probes, total
      <30s (SC-003), per-backend row `state/version/fix/probe_seconds`, human
      table per contracts/delegate-cli.md sample + `--json`
- [x] T020 [US2] Author `plugins/manifest-delegate/skills/delegate-setup/SKILL.md`:
      readiness report + user-config guidance (`delegation.{json,yml}` factory
      defaults, precedence); description ≈250 chars; zero prose cross-skill
      refs; no model IDs (gate-toggle docs land in US4)
- [x] T021 [US2] Append readiness smoke entry (one stubbed-unready backend,
      asserts remediation text present) to `smoke-catalog/manifest.yaml` via
      `configs/claude/scripts/smoke_test.py`

**Checkpoint**: US1 + US2 independently functional.

---

## Phase 5: User Story 3 — Second opinion across agents (P3)

**Goal**: Re-run a prior job's context on a different backend with clear
attribution, reusing US1 plumbing.

**Independent Test**: Complete a first pass on backend A, request a second
opinion on backend B; B receives shared context, both results attributed;
naming A again warns and offers alternatives (US3 AS1–AS2).

- [x] T022 [P] [US3] Write failing second-opinion tests in
      `tests/python/test_delegate_dispatcher.py`: `--second-opinion --of
      <job-id>` injects the referenced job's task context + attributed prior
      findings; same-backend request warns and lists other READY backends;
      kind forces read-only regardless of `--write`
- [x] T023 [US3] Implement `task --second-opinion --of <job-id>` in
      `plugins/manifest-delegate/scripts/delegate.py`: load referenced
      record, compose comparison context, force read-only, attribute both
      passes in output (FR-005)
- [x] T024 [US3] Extend `plugins/manifest-delegate/skills/delegate/SKILL.md`
      body with the second-opinion flow (frontmatter/description unchanged —
      budget already spent)
- [x] T025 [US3] Append second-opinion smoke entry (stub two backends, assert
      attribution of both) to `smoke-catalog/manifest.yaml` via
      `configs/claude/scripts/smoke_test.py`

**Checkpoint**: US1–US3 independently functional.

---

## Phase 6: Baseline Parity — standalone review incl. adversarial (SC-002 rows 3–4)

**Purpose**: Backend-generic replacement for `/codex:review` and
`/codex:adversarial-review` — required by FR-011/SC-002, ordered here by
plan.md's Phase 2 prescription. Not a spec user story: no story labels.

- [x] T026 [P] Write failing review tests in
      `tests/python/test_delegate_dispatcher.py`: diff assembly honors
      `--base`/`--scope auto|working-tree|branch`; `--adversarial` switches
      prompt and accepts free-text focus; kind=review forces registry
      read-only args; findings severity-first in the envelope; `--background`
      reuses the same job records as `task`
- [x] T027 Implement `review` subcommand (incl. `--adversarial [FOCUS...]`) in
      `plugins/manifest-delegate/scripts/delegate.py` per
      contracts/delegate-cli.md — findings never auto-applied (FR-008)
- [x] T028 Extend `plugins/manifest-delegate/skills/delegate/SKILL.md` body
      with review/adversarial usage (frontmatter unchanged)
- [x] T029 Append review smoke entry (stub backend over a fixture git repo
      with a working-tree change) to `smoke-catalog/manifest.yaml` via
      `configs/claude/scripts/smoke_test.py`

**Checkpoint**: full parity surface for rows 1–8 + 11–13 of the baseline table.

---

## Phase 7: User Story 4 — Optional finish-time review gate (P4)

**Goal**: Off-by-default soft Stop-hook gate: pauses completion at most once,
bounded budget, fail-open, never auto-applies — first plugin `hooks/` in this
repo.

**Independent Test**: Enable the gate with a stub backend, make a code edit,
declare completion → gate pauses once with findings; disable → no pause;
unready gate backend → completion proceeds with a note (US4 AS1–AS3).

- [x] T030 [P] [US4] Write failing gate tests in
      `tests/python/test_delegate_dispatcher.py`: disabled ⇒ allow; no code
      edits in finishing turn ⇒ allow; `stop_hook_active: true` in the Stop
      payload ⇒ immediate allow (harness re-entry indicator = at-most-once,
      D9); transcript edit-detection fixtures: finishing-turn window bounded
      by the last non-tool-result user message; Edit/Write/MultiEdit/
      NotebookEdit `tool_use` detected; a Bash-only turn ⇒ allow; at least
      one edit-detection fixture must be captured from a real Claude Code
      session transcript (one containing Edit/Write tool_use, one
      Bash-only); block
      reason text forbids tool use + requires asking the developer and ends
      "developer decides"; unready backend / timeout /
      malformed output ⇒ fail OPEN emitting a hook-JSON `systemMessage`
      naming the cause (developer-visible channel) plus a stderr note;
      configured budget >840
      capped to 840 and the cap reported; block decision JSON emitted exactly
      once; gate never writes files; setup-write format (D3): enabling the
      gate with no config creates `delegation.json`; with an existing `.yml`
      + PyYAML the `.yml` is updated in place; with a `.yml` and no PyYAML,
      `delegation.json` is written + precedence reported
- [x] T031 [US4] Implement `gate --transcript <path> [--stop-hook-active]`
      in `plugins/manifest-delegate/scripts/delegate.py` per D9:
      `--stop-hook-active` fast-path allow (at-most-once via the harness
      re-entry indicator); deterministic finishing-turn edit detection
      (contracts/delegate-cli.md algorithm); `gate`-kind job record as audit
      trail; one read-only review delegation within
      `review_gate.budget_seconds`; emit
      `{"decision":"block","reason":<findings>}` exactly once — reason
      severity-first, forbids tool use, requires asking the developer, ends
      "developer decides"; every fail-open path emits
      `{"systemMessage": "review gate skipped: <cause>"}`
      (defined-visibility channel) in addition to stderr
- [x] T032 [US4] Implement `setup` gate toggles in
      `plugins/manifest-delegate/scripts/delegate.py`:
      `--enable-review-gate [--gate-backend <id>]` / `--disable-review-gate`
      writing `review_gate.*` to `delegation.json` — the canonical
      setup-written format (created with factory defaults + change when no
      config exists); an existing `delegation.yml` is updated in place only
      when PyYAML is importable, else reported unreadable + `delegation.json`
      written and takes precedence (D3 migration rule); budget validated
      1–840, new state confirmed (US4/FR-006)
- [x] T033 [P] [US4] Author `plugins/manifest-delegate/scripts/stop_gate_hook.py`
      (reads the Stop stdin JSON and forwards `transcript_path` plus
      `--stop-hook-active` to `delegate.py gate`, decision passthrough.
      Disposition recorded 2026-08-16: the payload's other documented keys —
      `session_id`, `cwd`, `hook_event_name` — are deliberately NOT parsed.
      `gate` takes its job-record workspace from `os.getcwd()`, which the hook
      inherits from the harness, and exposes no flag to accept `cwd`; the other
      two feed no consumer. Parsing them would be dead surface, so the wrapper
      stays at the two load-bearing keys) and
      `plugins/manifest-delegate/scripts/session_hook.py` (SessionStart:
      capture session id + transcript path for transfer; SessionEnd: orphan
      gate/job cleanup — reap: kill recorded backend pgids of non-terminal
      jobs whose worker died) — thin wrappers, `--help` compliant (repo
      gate), each opening with the D11 version probe
- [x] T034 [US4] Author `plugins/manifest-delegate/hooks/hooks.json`: Stop
      hook timeout 900s, SessionStart/SessionEnd 5s, script paths via
      `${CLAUDE_PLUGIN_ROOT}` (plan.md Complexity Tracking row 1)
- [x] T035 [US4] Create `tests/bats/delegate_plugin.bats` with the NEW plugin
      hook-wiring gate (no repo precedent exists): hooks.json parses, declares
      exactly Stop/SessionStart/SessionEnd with timeouts 900/5/5, referenced
      scripts exist and are executable, `${CLAUDE_PLUGIN_ROOT}` used (no
      absolute paths), and the code-level gate-budget cap (≤840s) is asserted
- [x] T036 [US4] Extend
      `plugins/manifest-delegate/skills/delegate-setup/SKILL.md` body with
      gate enable/disable usage + the one-gate-at-a-time exclusivity warning
      (frontmatter unchanged)
- [x] T037 [US4] Append gate smoke entries (enabled: pauses once with stub
      findings; disabled: no pause) to `smoke-catalog/manifest.yaml` via
      `configs/claude/scripts/smoke_test.py`

**Checkpoint**: all four user stories + parity surface functional.

---

## Phase 8: Supersession (FR-011 / SC-002 / SC-006)

- [x] T038 Author `plugins/manifest-delegate/MIGRATION.md`: traceability table
      mapping ALL 13 baseline entry points (research.md baseline inventory) to
      their replacements + covering test each; uninstall instructions
      (`claude plugin uninstall codex`); gate-exclusivity rule (disable the
      baseline stop-gate before enabling the new one, D7); the
      read-only-by-default posture change vs baseline rescue (D8); the
      `--effort` disposition: baseline rescue's `--effort` is deliberately
      not a dispatcher flag — effort selection folds into `--model` tier
      selection, recorded so the SC-002 traceability row is settled;
      Principle VII activation note if ever published
- [x] T039 Verify supersession claims: every row in the MIGRATION.md table has
      a shipped replacement + test (zero uncovered — SC-002); `grep -r
      'openai-codex\|codex-plugin-cc'` over the repo returns nothing outside
      `specs/675-multi-agent-delegation/` (D7); record results in the PR
      description

---

## Phase 9: Registration & Generators (SKILL-NAMING.md lifecycle)

- [x] T040 Add the `manifest-delegate` entry (name, `source:
      ./plugins/manifest-delegate`, description, version 0.1.0, category
      `productivity`) to `.claude-plugin/marketplace.json`
- [x] T041 Add the bundle block (2 skills: delegate, delegate-setup) to
      `configs/claude/config/skill_policies.yml` and bump `expected_total:
      114` → `116` in the same change; and add a `delegation.*`
      protected-glob entry to `configs/claude/config/reconcile.yml` so a
      user-authored `delegation.yml` is never classified as an orphan by
      deploy-reconcile (Constitution V.4)
- [x] T042 Add `tool_policies` entries for `delegate` and `delegate-setup` in
      `configs/claude/config/command_config.yml` — each with
      allowed/forbidden tools, `parallel_agents`, `validation_tier`,
      `subagents` disposition (+ `subagent_trigger` if conditional) and
      `subagent_model: sonnet` (enforced by `tests/bats/subagent_policy.bats`)
- [x] T043 Run the generators and commit their output:
      `configs/claude/scripts/generate_skill_mirror.sh` (`.apm/skills/`
      mirror — never hand-edit);
      `configs/claude/scripts/generate_commands_doc.py` for `docs/COMMANDS.md`
      (`--check` gates CI) AND `--inject-guides` (writes
      `configs/gemini/GEMINI.md` + `AGENTS.md` — a different file set);
      `configs/claude/scripts/generate_cursor_rules.sh`; verify
      `configs/claude/scripts/generate_cursor_agents.py` picks up
      `delegate-runner` and the diff is intentional
- [x] T044 Update root `CLAUDE.md` (SPECKIT/agent-context block → feature 675
      status) staying ≤12900 bytes — compact the completed-674 entry if
      needed; make NO additions to `.claude/CLAUDE.md` (at its 3900-byte cap)
- [x] T045 Extend `tests/bats/delegate_plugin.bats` with registration gates:
      plugin.json declares the explicit `skills` array; marketplace.json entry
      present; skill_policies bundle block + count matches; registry↔
      `cli_agents` drift test (argv templates in
      `plugins/manifest-delegate/config/backends.json` stay consistent with
      `configs/claude/config/parallel_agent.yml` where both name the same
      binary — research.md D4); `services.yml` fixed-format reader stays
      matched to `write_services_config()` in `bootstrap/lib/config.sh`

---

## Phase 10: Polish & Cross-Cutting Verification

- [x] T046 [P] Complete the SC-004 fault-injection matrix in
      `tests/python/test_delegate_dispatcher.py` — one test per fault:
      missing binary, unauthenticated, disabled-by-workspace,
      disabled-by-user, timeout, malformed output, unknown backend, oversize
      context vs the transport bound AND vs the model-context bound (each
      error names the specific limit, never truncated); sandbox fault pair (D8): a
      `--write` delegation attempting an outside-workspace write and one
      attempting a destructive command (force-push/recursive delete) both
      come back denied/errored by the backend sandbox stub — never approved;
      assert every failure message is
      explicit, attributed, and actionable (100%)
- [x] T047 Run the budget/quality gates and fix regressions:
      `bats tests/bats/context_budget.bats` (frontmatter ≤29000, per-bundle
      ≤6000), skill-reference ratchet (warning stays ≤133, blocking 0),
      `bats tests/bats/skill_naming.bats` + `help_coverage.bats` +
      `subagent_policy.bats`,
      `configs/claude/scripts/constitution_check.py` on the new Python,
      `yamllint` on edited YAML
- [x] T048 Full-suite verification: `uv sync --project configs/claude` + `git
      submodule update --init` first (fresh-worktree requirement), then
      `pytest tests/python/` and `bats tests/bats/`; then the Verify gate:
      `python3 configs/claude/scripts/smoke_test.py run --tier Lite` must
      exit 0 (executing the appended delegate smoke entries), and run
      /spec-audit-tasks against this tasks.md — all green, zero regressions
- [x] T049 Execute `specs/675-multi-agent-delegation/quickstart.md` end to end
      (stub backends where real ones are unready; note: gemini CLI retired,
      cursor usage-limited — real-CLI checks run on codex + agy + claude),
      including the D11 no-bootstrap check: install → readiness → one stubbed
      delegate in a hermetic environment with system `python3` only (no uv,
      no PyYAML, no Manifest deploy — SC-005); plus the read-only
      mutation-denial spot check on real CLIs (D8): a read-only delegation
      instructed to modify a file must come back denied on each available
      backend (codex/claude/agy), and
      record results in the PR description
- [ ] T050 Run the mandatory Constitution II Tier-1 cross-verification on the
      implementation PR: `manifest parallel-agent --json --validate --timeout
      900 --review <absolute changed paths>` — judge completed agents only
      (codex + agy; cursor limited until 2026-08-12), resolve findings before
      merge

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)** → nothing
- **Foundational (P2)** ← Setup; **blocks all user stories**
- **US1 (P3)** ← Foundational — MVP; T009 before T010–T013 (test-first)
- **US2 (P4)** ← Foundational (readiness reads registry + config only);
  ordered after US1 per plan.md prescription
- **US3 (P5)** ← US1 (reuses task plumbing + job records)
- **Parity review (P6)** ← US1 (reuses job records + envelope)
- **US4 (P7)** ← US1 (gate runs a review delegation) + Parity review
  (gate delegates kind=review); T035 creates `delegate_plugin.bats`, T045
  extends it (sequential, same file)
- **Supersession (P8)** ← all capability phases (13-row map must point at
  shipped surfaces)
- **Registration (P9)** ← both SKILL.md files final (T015/T020/T024/T028/T036)
  — generators consume frontmatter; T043 after T040–T042
- **Polish (P10)** ← everything; T050 last (runs on the final PR diff)

### Within Each User Story

Failing tests first → dispatcher implementation → skill/agent authoring →
smoke entry. Same-file dispatcher tasks (T010–T013, T019, T023, T027,
T031–T032) are sequential — `delegate.py` is one file; only [P]-marked tasks
touch disjoint files.

### Parallel Opportunities

- T003 ∥ T005 (registry file vs test file) after T002
- T009 ∥ T014 ∥ T016 at US1 start (tests, references, agent — disjoint files)
- T018 (US2 tests) ∥ any remaining US1 skill-authoring task
- T030 ∥ T033 at US4 start (tests vs hook scripts)
- T046 ∥ T038 (fault matrix vs MIGRATION.md)
- Different user stories can proceed in parallel after Foundational if
  staffed, at the cost of serializing every edit to `delegate.py` AND to
  `tests/python/test_delegate_dispatcher.py` (T005/T018/T022/T026/T030/T046
  share that file — their [P] marks hold only within their own phase's
  window, like T035/T045) — the plan's prescribed order
  (US1→US2→US3→review→US4) is the low-conflict path

---

## Parallel Example: User Story 1

```bash
# After Phase 2 checkpoint, launch together (disjoint files):
Task: "T009 failing job-lifecycle tests in tests/python/test_delegate_jobs.py"
Task: "T014 four reference files under plugins/manifest-delegate/skills/delegate/references/"
Task: "T016 agents/delegate-runner.md thin forwarder"
# Then serially: T010 → T011 → T012 → T013 (all edit scripts/delegate.py)
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phases 1–2 (skeleton, registry, config, job store, envelope)
2. Phase 3 (US1) → validate independently via `pytest
   tests/python/test_delegate_jobs.py` + the delegate smoke entries
3. STOP and demo: delegation to all three backends with job management

### Incremental Delivery

Each subsequent phase (US2 → US3 → review parity → US4 → supersession →
registration) is independently verifiable at its checkpoint; registration
(Phase 9) is deliberately last-but-one so budgets/generators run once against
the final skill surface, and Phase 10 gates the PR (Constitution II Tier-1
cross-verification, T050).

### Sub-agent policy (handoff mandate)

Any sub-agent dispatched while implementing these tasks is pinned to
**Sonnet** (`~/.claude/references/sub-agent-dispatch.md`); a premium-model
switch requires asking the user first.
