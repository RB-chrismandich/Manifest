# Phase 0 Research: Multi-Agent Delegation Plugin

**Feature**: `675-multi-agent-delegation` | **Date**: 2026-08-05

Inputs: spec.md (clarified 5/5), baseline inventory of the externally installed
`openai/codex-plugin-cc` v1.0.6 (marketplace cache
`~/.claude/plugins/cache/openai-codex/codex/1.0.6/`), repo invocation
infrastructure (`configs/claude/scripts/agents/runners.py`, `agents/config.py`,
`parallel_agent.yml`), bootstrap install/toggle mechanics, and the live catalog
budget/registration gates. All facts below were read from files or measured by
running the gates on 2026-08-05.

---

## Baseline capability inventory (parity target)

The installed baseline (v1.0.6) exposes, all dispatched through one Node script
(`node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" <subcommand>`):

| # | Baseline entry point | Kind | Capability |
|---|----------------------|------|------------|
| 1 | `/codex:rescue` | command → `codex-rescue` agent | Delegate task (fg/bg, `--resume`/`--fresh`, `--model`, `--effort`, write-capable by default) |
| 2 | `/codex:setup` | command | Readiness check + install offer + `--enable/--disable-review-gate` |
| 3 | `/codex:review` | command | Native code review of local git state (fg/bg, `--base`, `--scope`) |
| 4 | `/codex:adversarial-review` | command | Adversarial review with free-text focus, JSON schema output |
| 5 | `/codex:status` | command | Job list/detail, `--wait`, `--timeout-ms`, `--all` |
| 6 | `/codex:result` | command | Stored final output of a finished job |
| 7 | `/codex:cancel` | command | Cancel active job (`turn/interrupt` + unconditional local cancel) |
| 8 | `/codex:transfer` | command | Claude session JSONL → resumable Codex thread (app-server import RPC) |
| 9 | Stop hook (900s) | hook | Optional stop-time review gate, default OFF, ALLOW/BLOCK verdict |
| 10 | SessionStart/End hooks (5s) | hooks | Env capture (session id, transcript path); orphan-job + broker cleanup |
| 11 | `codex-cli-runtime` | internal skill | Runner conventions for the rescue agent |
| 12 | `codex-result-handling` | internal skill | Result envelope + non-autonomy presentation rules |
| 13 | `gpt-5-4-prompting` (+3 refs) | skill | Model-specific prompting guidance |

Mechanism notes that informed decisions below:

- **Job state** lives at `${CLAUDE_PLUGIN_DATA}/state/<slug>-<sha256(cwd)[:16]>/`:
  `state.json` (light index, jobs pruned to 50, `config.stopReviewGate: false`
  default), `jobs/<id>.json` (full result + rendered), `jobs/<id>.log`,
  `broker.json`.
- **Broker**: per-workspace detached Node process holding one JSON-RPC
  connection to `codex app-server` over a Unix socket; serializes clients;
  `turn/start`, `review/start`, `turn/interrupt` (cancel bypass),
  `turn/completed`. Resume = look up `threadId` from the job index.
- **Cancel** marks the local record cancelled unconditionally, independent of
  interrupt success.
- **Gate** is a Stop hook: one `spawnSync` per Stop event, 15-min hard timeout,
  fails closed to "run manually or bypass", never edits files.
- plugin.json declares **no** component arrays (auto-discovery) — this repo
  requires explicit `skills` arrays, so parity packaging differs deliberately.

---

## D1 — Job-management mechanism

**Decision**: One-shot CLI executions wrapped by a plugin-native job manager
(per-job record files + detached process groups). No persistent broker.

**Rationale**:

- The baseline's broker exists because `codex app-server` offers a rich
  JSON-RPC session surface. Neither `claude` nor `agy` has an equivalent, so a
  generalized broker would be codex-only complexity contradicting FR-016
  (backend-generic surfaces).
- Resumable follow-ups do not need a live process. All three CLIs resume
  non-interactively (verified via `--help` on installed binaries 2026-08-05):
  codex `codex exec resume <SESSION_ID|--last> [PROMPT]`; claude
  `claude -p --resume <id>` / `--continue` (+ `--fork-session`); agy
  `agy -p --conversation <ID>` / `--continue`. Storing the session/thread id in
  the delegation record is sufficient — the same identity model the baseline
  uses (`threadId` in the job index).
- Repo convention is one-shot exec (`parallel_agent.yml` `cli_agents`:
  `codex exec --full-auto --color never --output-last-message {output_file}`,
  `claude --model {m} -p {prompt}`, `agy --model {m} --print {prompt}`), so the
  invocation shapes are already proven here.
- Background capability (FR-014) maps to a two-process design
  (technical-review hardening 2026-08-05): the launcher creates the job
  record (`queued`), spawns a detached internal **worker** (`delegate.py`'s
  hidden worker mode, own session via `setsid`), prints the job id, and
  exits. The worker stays alive as the backend's supervisor: it spawns the
  backend CLI in its own process group, owns the budget timeout (kills the
  process group on expiry), captures output into the job dir, writes the
  final envelope atomically (temp file + `os.replace`), and sets the
  terminal state exactly once. *status* = record file + worker/backend
  liveness; *result* = captured last-message/stdout file; *cancel* = kill
  the backend process group, then compare-and-replace the record to
  `cancelled` only while it is still non-terminal — an already-terminal
  record is left untouched and its state reported (deliberate divergence
  from the baseline's unconditional cancel: the completion/cancel race
  resolves to whichever terminal write lands first). Compare-and-replace is
  serialized through a per-job exclusive lock (`fcntl.flock` on
  `<job-dir>/.lock`): the state re-read and the terminal write share one
  critical section, so a bare re-read + `os.replace` TOCTOU window cannot
  let completion and cancel overwrite each other (technical-review finding
  2026-08-05). Reader paths double as a **reaper**: a status/result/cancel
  read that finds a dead worker with a recorded live backend `pgid` kills
  that process group before marking the record `failed` — a dead supervisor
  must not leave the backend running (FR-012 no-orphan rule); the
  SessionEnd hook performs the same sweep for every non-terminal job.
- Clean-timeout requirement (FR-012, edge case "no orphaned processes") is
  easier to guarantee with a process-group kill than with broker lifecycle
  management (the baseline needs SessionEnd cleanup + pid files + liveness
  probes to achieve the same).

**Alternatives considered**:

- *Generalize the persistent broker*: rejected — codex-only upstream protocol;
  three daemons (or one polyglot daemon) to babysit; violates the extensible
  registry goal (a new backend would need a broker adapter, i.e. a redesign).
- *Claude Code native background Bash only (no records)*: rejected — status/
  result/cancel must survive the invoking turn and be inspectable from a later
  turn or another surface (FR-014), which requires on-disk records; also
  unusable from non-Claude harnesses.
- *Reuse `runners.py` CLIAgent directly*: rejected as a hard dependency —
  SC-005 requires the plugin to work from a marketplace-only install where
  `~/.claude/scripts/agents/` may be absent (see D5). Invocation *templates*
  are reused; the code is not imported.

**Session transfer (baseline #8) under this decision**: codex transfer is
implemented as a short-lived direct `codex app-server` invocation performing
the external-session-import RPC (the baseline's `importExternalAgentSession`
path minus the broker), returning a `threadId`. claude and agy have no
transcript-import RPC: per FR-015, the plugin says so and re-sends distilled
context as a new delegation instead — disclosed, never silent. Registry
`transfer.method` values form a **fixed capability vocabulary** (currently
`app_server_import` | `null`): a future backend that fits an existing method
is entry-only per FR-016, while a wholly new transfer protocol is a
deliberate dispatcher extension (new method value + handler) outside
FR-016's entry-only guarantee — which covers the delegation, readiness,
second-opinion, review-gate, and configuration surfaces (technical-review
scoping 2026-08-05).

## D2 — Delegation records & transcript persistence (observability)

**Decision**: Per-job record directories under
`~/.claude/.agent_outputs/delegations/<workspace-slug>-<sha256(cwd)[:16]>/<job-id>/`
containing `record.json` (metadata + normalized result envelope), `output.txt`
(backend's final message), and `job.log` (timestamped progress + raw
stdout/stderr tail). Retention: prune to the newest 50 jobs per workspace on
write (matching the baseline's `MAX_JOBS=50` and the existing
`output.keep_last: 50` convention in `parallel_agent.yml`).

**Rationale**:

- `~/.claude/.agent_outputs/` is the repo's established runtime-artifact
  location (parallel-agent logs live there; `output.directory` in
  `parallel_agent.yml` declares it with a keep-last policy). Runtime state is
  deliberately *not* deployer-owned, so Constitution I/V are satisfied (a
  deployed tree stays a build output; user-scope state lives where no deploy
  mechanism claims ownership).
- One directory per job (instead of a shared mutable `state.json` index like
  the baseline) means no shared-write serialization problem across concurrent
  delegations (spec edge case: two delegations in one session must not
  interleave) — each job writes only inside its own dir; listing = readdir.
- `record.json` carries: job id, backend, kind (task/review/second-opinion/
  gate), status (queued→running→completed/failed/cancelled/timeout), pgid,
  backend session/thread id (for resume), model tier, budget, timestamps,
  workspace root, and the FR-002 result envelope. `job.log` preserves enough
  transcript for post-hoc debugging without persisting full raw transcripts.
- Env override `MANIFEST_DELEGATIONS_DIR` for tests (mirrors the
  `MANIFEST_CONFIG_DIR` precedent in `agents/config.py`).

**Alternatives considered**: `${CLAUDE_PLUGIN_DATA}/state/` (baseline's
location) — rejected: only populated under Claude Code sessions with the
plugin's SessionStart env capture; the dispatcher must also be invocable from
other harnesses and plain shells. A shared `state.json` index — rejected:
reintroduces serialized shared writes for marginal listing speed.

## D3 — User configuration file

**Decision**: `~/.claude/config/delegation.{json,yml}`, resolved with the
existing precedence rule (explicit path > `$MANIFEST_CONFIG_DIR` >
`~/.claude/config/`). Factory defaults (used when absent) are compiled into
the dispatcher. Stdlib-only parsing policy (spec-review finding, 2026-08-05):
`delegation.json` parses everywhere; `delegation.yml` is honored when PyYAML
is importable by the invoking interpreter, and a `.yml` present without
PyYAML is the FR-013 "unreadable" case — reported + factory defaults (`.json`
wins if both exist). **Setup-written format (technical-review 2026-08-05):
JSON is canonical — `setup` writes `delegation.json`.** Migration for an
existing `delegation.yml`: when PyYAML is importable, `setup` updates the
`.yml` in place (YAML is written only with PyYAML confirmed present; the
user's chosen format is respected and no shadowing `.json` is created);
without PyYAML, `setup` reports the `.yml` as unreadable, writes
`delegation.json` (factory defaults + the requested change), and states that
`.json` now takes precedence — matching runtime behavior, where the
unreadable `.yml` was already inert. Schema (contract in
`contracts/delegation-config.schema.json`):

```yaml
default_backend: codex          # factory default
review_gate:
  enabled: false                # factory default: off
  backend: null                 # null → default_backend
  budget_seconds: 600
backends:
  codex:      { enabled: true, model: null, budget_seconds: 600 }
  claude:     { enabled: true, model: null, budget_seconds: 600 }
  antigravity: { enabled: true, model: null, budget_seconds: 600 }
```

**Rationale**:

- Same directory + resolution mechanism as every other user-facing config in
  this workspace (`agents/config.py::resolve_config_path`), and the
  `services.yml` precedent proves `~/.claude/config/` hosts non-deployed
  user-state files. Constitution V.4 explicitly blesses "a user-scope file no
  package owns" for user state; `delegation.yml` is never shipped in `configs/`
  and never written by a deployer.
- **Error policy differs from `Config._load_config()` deliberately**: the
  agents config raises `ConfigError` on malformed YAML; FR-013 mandates
  *report-and-proceed-on-factory-defaults* for this file. The dispatcher warns
  on stderr with the parse error and continues on factory defaults. This
  divergence is required by the spec and is documented in the contract.
- Precedence (FR-013): workspace `services.yml` `enabled: false` beats a user
  `delegation.yml` `enabled: true`; the readiness report names which layer
  blocked a backend ("disabled by workspace services.yml" vs "disabled by user
  delegation.yml").
- `model` values are **tier names** (per `harness-routing.md` rule 1: raw model
  IDs live only in `parallel_agent.yml` `model_tiers`), with verbatim
  passthrough for values that aren't known tiers (the devin precedent).
  Factory default tier per backend follows FR-009's economical-model rule:
  codex `auto`, claude `sonnet`, antigravity `flash` (the
  `harness_routing.*.default_model_tier` values).

**Alternatives considered**: XDG `~/.config/manifest/` — rejected: nothing else
in this workspace lives there, and `MANIFEST_CONFIG_DIR` already provides
relocation. Extending `services.yml` — rejected: that file is bootstrap-written
(deployer-adjacent) and per-service, not per-delegation-policy; mixing owners
violates Constitution V.5 single ownership.

## D4 — Backend registry

**Decision**: A declarative registry file shipped **inside the plugin**
(`plugins/manifest-delegate/config/backends.json` — JSON so the stdlib-only
dispatcher parses it unconditionally; spec-review finding 2026-08-05), one
entry per backend, seeded with exactly `codex`, `claude`, `antigravity`
(alias `agy`). Entry
schema (contract in `contracts/backend-registry.schema.json`): identity
(id/aliases/display name), invocation (one-shot argv template, resume argv
template, model-flag template, session-id capture rule), readiness probes
(binary name, version command, non-interactive auth probe, install + login
remediation text), sandbox profile (read-only vs write-enabled flag sets),
prompting reference (path to the per-backend guidance file), and
`services_key` (the `services.yml` toggle it honors).

Seed invocation facts (verified against installed CLIs and
`parallel_agent.yml` `cli_agents`):

| Backend | One-shot | Resume | Read-only mode | Auth probe |
|---|---|---|---|---|
| codex | `codex exec --json --color never --output-last-message <f> [-m <model>] <prompt>` (sandbox args from D8 appended; `--json` streams JSONL events for session capture) | `codex exec resume <id> <prompt>` | `--sandbox read-only` | `codex login status` (fallback: `~/.codex/auth.json` presence per services.yml) |
| claude | `claude -p [--model <model>] --output-format json <prompt>` | `claude -p --resume <id> <prompt>` | sandbox-enabled `--settings` + `--permission-mode plan` + write-tool denylist (D8) | `claude --version` + a 1-token `-p` probe or auth status; final probe resolved by T003's acceptance check against a real authenticated + logged-out CLI (non-interactive, ≤10s) |
| antigravity | `agy -p [--model <model>] --output-format json <prompt>` | `agy -p --conversation <id> <prompt>` | `--sandbox --mode plan` (sandbox retained in write mode too — D8) | `agy models` (the bootstrap auth probe) |

Session-id capture: claude/agy emit `--output-format json` payloads carrying
session/conversation ids (`json_field` capture). codex runs with `--json`,
which streams JSONL events on stdout (technical-review hardening
2026-08-05): the thread id is parsed from the version-gated `thread.started`
event (`jsonl_event` capture — the event exists only on newer codex CLIs;
when absent, `session_ref` stays null and resume unavailability is disclosed
per FR-015, never treated as an error), while the result body still comes
from `--output-last-message`. Each registry
entry declares *how* to extract it, so FR-015 stays registry-driven. The
JSONL parser is tested against fixtures captured from real
`codex exec --json` runs, including an older-CLI sample without
`thread.started`.

Input transport (technical-review hardening 2026-08-05): each registry entry
declares `input.transport` (`stdin` preferred — prompts piped to the CLI's
stdin then EOF; `temp_file` — a 0600 file inside the job dir substituted at
`{prompt_file}`; `argv` only for short prompts) plus `max_payload_bytes`
(transport cap) and `max_context_bytes` (best-known model-context bound,
nullable). Large prompts never ride argv — the repo's llm-invoke-stdin
convention (ARG_MAX-safe, keeps payloads out of `ps`) generalized to the
registry. The dispatcher validates context against both bounds and names the
specific limit exceeded, never truncating; the exact stdin invocation per
CLI is confirmed against the real binaries by T003's acceptance check before
`input.transport` is seeded (`codex exec -` reads stdin; `claude -p` reads
stdin when no prompt argument is given; agy's stdin behavior is unverified
until that check runs), and T049's quickstart pass re-verifies delivery end
to end.

**Rationale**: FR-016 verbatim — adding a backend must be a registry entry +
readiness probe, no surface redesign. A registry entry consumed by one dispatcher
achieves that; every surface (delegate, readiness, second-opinion, gate,
config) iterates the registry rather than switching on names. The cross-CLI
resume asymmetry (subcommand vs flag) is exactly why invocation shapes belong
in data, not code.

**Alternatives considered**: reusing `parallel_agent.yml` `cli_agents` as the
registry — rejected: it lacks readiness/remediation/sandbox/prompting fields,
is deployed-tree-resident (breaks marketplace-only install, SC-005), and
serves a different consumer. Instead, a bats drift test asserts the plugin
registry's argv templates stay consistent with `cli_agents` where both name
the same binary.

## D5 — Engine placement & language

**Decision**: A self-contained, stdlib-only Python 3 dispatcher inside the
plugin, entered at `plugins/manifest-delegate/scripts/delegate.py`, with
subcommands `task`, `review` (incl. `--adversarial`), `status`, `result`,
`cancel`, `setup`, `transfer`, `gate`, `resume-candidate`. Hook scripts are thin
Python entries in the same `scripts/` dir invoked via `${CLAUDE_PLUGIN_ROOT}`.

**Amended 2026-08-08 (implementation)**: originally "a single self-contained
Python 3 dispatcher … `scripts/delegate.py`". The implementation reached 3,440
lines, against the Code Constitution's 500-line file ceiling (CON-002). The
ceiling is a repo-wide gate with no per-path exemption mechanism, and the
alternative — an inline whole-file `constitution: exempt C-SIZE` marker — would
have grandfathered the largest file in the plugin rather than fixed it.

The implementation therefore lives in a sibling package,
`plugins/manifest-delegate/manifest_delegate/`, split along the responsibility
seams the single file already had as banner comments: `constants`, `registry`,
`config`, `jobstore`, `envelope`, `backend`, `process`, `worker`, `task`,
`review`, `jobs_cli`, `transfer`, `readiness`, `gate`, `setup`, `cli`. Every
module is under the ceiling.

What this does **not** change: still stdlib-only, still one process, still no
backend-name branching, still installed by the ordinary marketplace flow (the
package ships inside the plugin bundle; SC-005 is unaffected). `scripts/
delegate.py` remains the executable entry point every hook, skill, and contract
names, so no external interface moved — it runs the D11 version probe, puts the
plugin root on `sys.path`, and re-exports the package.

"Self-contained" was always about the dependency boundary (no imports from
`~/.claude/scripts/`, no PyYAML requirement), not about file count; the package
satisfies it identically. Cross-module references inside the package are
qualified (`registry.load_registry`) rather than `from .registry import …`, so
the import graph tolerates the cycles the single file had for free and a test
patching a module-level constant patches the module that owns it.

**Rationale**:

- **SC-005 forces self-containment**: "a fresh workspace can install and invoke
  it using only the standard marketplace flow" — the marketplace installs only
  the plugin bundle, so the engine cannot import `~/.claude/scripts/agents/*`
  and cannot assume PyYAML. Workspace-config reads under that rule:
  `services.yml` **enable flags** are extracted with a fixed-format line reader
  matched to `write_services_config()`'s generator-owned layout (bats-gated
  against that generator), so the FR-013 MUST — workspace disables outrank
  user enables — holds unconditionally; `parallel_agent.yml` `model_tiers` is
  consulted only when PyYAML is importable, else tier names pass through
  verbatim (the devin precedent). When deployed config is absent entirely,
  compiled factory defaults apply. The `manifest-docker` bundle set this
  self-contained precedent.
- Python over the baseline's Node: repo standards (pytest/bats harnesses, code
  constitution Python annex, shellcheck'd bash), and no Node runtime dependency
  for a plugin whose job is spawning CLIs. Baseline content is Apache-licensed
  OpenAI code; we write original code and original prompting guidance — no
  vendoring (also keeps NOTICE obligations out of scope).
- Single dispatcher mirrors the baseline's proven `codex-companion.mjs` shape:
  every skill/hook shells to one entry point, which keeps the skills thin and
  the behavior testable without a Claude session.

**Alternatives considered**: engine in `configs/claude/scripts/` (deployed) —
rejected on SC-005; splitting per-backend runner scripts — rejected: the
registry makes one dispatcher sufficient, and N scripts multiply the `--help`
coverage, shellcheck, and constitution surfaces.

## D6 — Skill surface & catalog budgets

**Decision**: New bundle `manifest-delegate` with exactly **2 user-facing
skills** + 1 agent + hooks; per-backend prompting guidance ships as skill-body
`references/` files, not skills.

| Component | Purpose |
|---|---|
| `skills/delegate/SKILL.md` | Delegate/second-opinion/follow-up + standalone review incl. adversarial (baseline rows 3–4) + job verbs (status/result/cancel) + transfer; backend a parameter; `references/` carry per-backend prompting + result-envelope conventions |
| `skills/delegate-setup/SKILL.md` | Readiness report (all backends) + review-gate enable/disable + config-file guidance |
| `agents/delegate-runner.md` | Thin forwarder subagent (model: sonnet, Bash-only) — the baseline `codex-rescue` non-autonomy contract generalized: one dispatcher call, stdout verbatim, no independent solving |
| `hooks/hooks.json` | Stop (review gate) + SessionStart (env capture for transfer) + SessionEnd (orphan-job cleanup) |

**Measured budget position (2026-08-05, gates run live)**:

- Catalog-wide frontmatter: 25110/29000 → **3890 chars headroom**; two ~250-char
  descriptions fit without offsets.
- Per-bundle cap 6000: a new bundle starts at 0 — no risk.
- Cross-skill reference ratchet: warning tier **133/133, zero headroom**
  (`skill_reference_baseline.json`); blocking tier 0/35. Consequence: the new
  skill bodies must reference other skills **zero** times in prose (use file
  paths, which are informational-only), or an equal number of existing warning
  refs must be removed in the same PR. This is a hard planning constraint.
- `.claude/CLAUDE.md` is at its 3900-byte cap and root `CLAUDE.md` has 193
  bytes headroom — the agent-context update must fit by compacting the
  completed-674 entry.

**Alternatives considered**: mirroring the baseline's 8 `commands/` — rejected:
this repo's registration, generation, and test apparatus (skill_policies,
tool_policies, mirror/doc/rules generators, naming gates) covers *skills*;
commands would be an unregistered parallel surface. Job verbs as separate
skills (`delegate-status`, `delegate-cancel`, …) — rejected: 4 more
frontmatter entries + 4 more tool_policies rows for argument-sized variations;
the dispatcher already exposes them as subcommands.

## D7 — Supersession & migration

**Decision**: Ship `plugins/manifest-delegate/MIGRATION.md` mapping **all 13**
baseline entry points (table above) to their replacements; supersession
completes when the user uninstalls the external plugin
(`claude plugin uninstall codex` / marketplace removal), which the migration
note instructs. Verified: zero references to `openai-codex`/`codex-plugin-cc`
exist in the repo outside spec 675 — no bootstrap or config change is needed
to sever a dependency, because none exists. Transitional coexistence is safe
(disjoint namespaces `/codex:*` vs `/manifest-delegate:*`) with one documented
exception: only one stop-gate may be enabled at a time (both register Stop
hooks); the migration note requires disabling the baseline gate before
enabling the new one. SC-002/SC-006 are verified by a traceability table in
the migration note (every baseline row → replacement + test).

## D8 — Sandboxing & write-gating (FR-008)

**Decision**: Delegations run read-only by default; `--write` opts in. The
registry `sandbox` object carries a concrete per-backend security profile
(technical-review hardening 2026-08-05):

- **codex** — read-only `--sandbox read-only`; write `--sandbox
  workspace-write` (explicit, in preference to the `--full-auto` alias).
- **claude** — BOTH modes launch with sandbox-enabled settings
  (`--settings '{"sandbox":{"enabled":true}}'`) and a constrained surface:
  read-only runs `--permission-mode plan` (denies mutating actions,
  including Bash-mediated writes — a tool denylist alone would leave Bash
  as a mutation path; technical-review finding 2026-08-05) plus the
  write-tool denylist (`--disallowedTools "Write,Edit,NotebookEdit"`);
  write keeps the sandbox settings and swaps to
  `--permission-mode acceptEdits`. No `--add-dir` beyond the workspace in
  either mode — edits stay sandbox-scoped to the workspace directory.
- **antigravity** — `--sandbox` is retained in BOTH modes and the mode flag
  is always explicit: read-only `--sandbox --mode plan` (the CLI's
  read-only planning mode — bare `--sandbox` does not select it;
  technical-review finding 2026-08-05); write `--sandbox --mode
  accept-edits` (accept-edits operates inside the sandbox, never replaces
  it).

**Scope of `--write` (spec-review clarification 2026-08-05)**: it
pre-authorizes only sandbox-scoped, non-destructive workspace edits — the
class those modes auto-allow. Approval-escalating actions (network access,
paths outside the workspace, force-pushes/deletes that trip the backend's
approval boundary) remain **denied** by each CLI's non-interactive mode: an
unattended run errors rather than approves, so the plugin never grants
approval on the user's behalf (FR-008, destructive-operation edge case).

**Enforcement is layered — schema AND runtime**: dangerous tokens (anything
matching `dangerously|bypass`, covering `--dangerously-*` and
permission-bypass modes) are rejected by pattern constraints on every argv
template in `backend-registry.schema.json` (invoke, resume, model_args,
sandbox args) AND re-validated by the dispatcher when it loads the registry —
a registry containing such a token refuses to run (exit 2), so a hand-edited
registry cannot smuggle a bypass past the schema. The review-gate, review,
and second-opinion kinds force read-only regardless of flags.

**Fault tests (SC-004)**: the fault-injection matrix includes a `--write`
delegation attempting (a) a file write outside the workspace root and (b) a
destructive command (force-push / recursive delete) — both must come back
denied or errored by the backend's own sandbox, never approved by the
dispatcher.

This inverts the baseline's write-by-default rescue posture to
satisfy FR-008; the migration note calls out the behavior change.

## D9 — Review gate semantics (soft gate)

**Decision**: Stop hook (Python, plugin-local) implementing the clarified soft
gate: when enabled and the finishing turn made code edits, run one read-only
review delegation on the gate backend, bounded by `review_gate.budget_seconds`
(default 600); present findings by emitting the Stop-hook block decision
**once**.

**Exact mechanics (technical-review hardening 2026-08-05)**:

- **Stop payload**: the hook receives stdin JSON with `session_id`,
  `transcript_path`, `cwd`, `hook_event_name: "Stop"`, and
  `stop_hook_active` (bool). The wrapper forwards `transcript_path` and the
  `stop_hook_active` flag to `delegate.py gate`.
- **At-most-once via the harness re-entry indicator**: `stop_hook_active:
  true` means this Stop event fires while the session is already continuing
  from a prior Stop-hook block — the gate allows immediately, before any
  other work. This replaces a bespoke completion-attempt fingerprint as the
  enforcement mechanism; a `gate`-kind job is still recorded per run as the
  audit trail.
- **Deterministic edit detection**: scan the transcript JSONL for the last
  user message that is not a tool-result carrier; the finishing turn = all
  entries after it; code edits are present iff any assistant `tool_use` in
  that window names `Edit`, `Write`, `MultiEdit`, or `NotebookEdit`. Bash
  commands are deliberately not classified — under-triggering is acceptable
  because the gate is best-effort and fail-open.
- **Block reason contract**: the emitted
  `{"decision":"block","reason":<text>}` reason presents findings
  severity-first, instructs the session to make **no tool calls and no
  edits** in response, and requires it to relay the findings and ask the
  developer how to proceed.

**Budget/timeout alignment
(spec-review finding 2026-08-05)**: the hook's registered timeout is 900s and
the effective gate budget is validated to ≤ 840s (900 − 60s cleanup/present
overhead); a larger configured value is capped and the cap is reported, so
the hook's outer timeout can never truncate a promised budget. All failure
modes (backend unready, timeout, malformed output) fail **open**, reporting
the cause through the hook-JSON `systemMessage` field — the harness's
defined developer-visible channel — plus a stderr note — the spec says the
gate must not block completion indefinitely,
whereas the baseline fails closed to a manual-bypass message. Never
auto-applies fixes; findings end with "developer decides".

## D10 — Delegation prompting (FR-007)

**Decision**: Original per-backend guidance files under
`skills/delegate/references/`: `prompting-codex.md` (operator-style,
block-structured contracts — the conventions the baseline's `gpt-5-4-prompting`
teaches, rewritten, not copied), `prompting-claude.md` (direct task +
constraints + output contract; no XML ceremony needed), `prompting-agy.md`
(concise instruction + explicit output format). The
dispatcher injects the shared result-envelope contract (FR-002) into every
delegation prompt so all backends return comparable structure; the skill body
tells the session to load the matching reference before composing a prompt.
**Envelope extraction is mechanical, never inferential (technical-review
finding 2026-08-05)**: the injected contract requires the backend to END its
final message with a fenced JSON block conforming to
`result-envelope.schema.json`; the dispatcher extracts the last fenced JSON
block from the captured output, validates required fields with stdlib
`json`, and performs no semantic parsing of prose — a missing or invalid
block ⇒ `outcome: failure` "backend returned nothing usable" with the raw
output preserved at `raw_output_path` (SC-004; a summary is never
fabricated).
The baseline's `--effort` flag is deliberately not carried as a dispatcher
flag: effort selection folds into `--model` tier selection, and MIGRATION.md
records that disposition for the SC-002 traceability row (T038).

## D11 — Python runtime floor (marketplace install without bootstrap)

**Decision**: Target **Python 3.9** as the dispatcher/hook floor — the
oldest interpreter guaranteed on the bootstrap-supported platform set — with
an early version probe and exact remediation, instead of shipping a runtime.
(Added by technical review 2026-08-05; supersedes the plan draft's 3.11+.)

**Rationale**:

- SC-005's marketplace-only install cannot assume anything Manifest
  bootstrap provides (no uv, no Homebrew Python, no PyYAML). The only
  guaranteed interpreter is the system `python3`: macOS Command Line Tools
  ships 3.9.x at `/usr/bin/python3`, and the bootstrap-supported Linux
  distributions ship ≥3.9 in their currently supported releases.
- All plugin Python (dispatcher + hook scripts) is syntax-constrained to
  3.9: no `match`/`case`, no PEP 604 `X | Y` annotations evaluated at
  runtime, no 3.10+ stdlib APIs.
- **Early version probe**: the first executable statements of `delegate.py`
  and each hook script check `sys.version_info` using only syntax even
  Python 2.7 parses, and exit 2 with the exact remediation before anything
  else (including `--help` handling): `manifest-delegate requires Python >=
  3.9 (found X.Y). Fix: macOS: xcode-select --install (or brew install
  python3); Debian/Ubuntu: sudo apt install python3; other: install Python
  3.9+ and re-run.`
- Verification: an install test on a machine (or hermetic environment)
  without Manifest bootstrap — system `python3` only, no uv, no PyYAML —
  exercises install → readiness → delegate (quickstart step, SC-005).

**Alternatives considered**: shipping a runtime with the plugin — rejected:
the marketplace mechanism has no supported payload/install-hook path for
interpreter distribution, and vendoring one violates the thin-bundle model.
Pinning 3.11+ — rejected: not guaranteed on stock macOS CLT or older
supported Linux; it would make SC-005's fresh-workspace install fail on a
stock machine.

---

## Resolved Technical-Context unknowns

| Unknown | Resolution |
|---|---|
| Job management | D1: one-shot + record-dir job manager, no broker |
| Persistence | D2: `~/.claude/.agent_outputs/delegations/`, keep-last 50 |
| User config location/schema | D3 |
| Registry shape | D4 |
| Language/placement | D5: self-contained Python in plugin |
| Skill surface vs budgets | D6: 2 skills; ref-ratchet zero-headroom constraint |
| Supersession path | D7 |
| Write gating | D8 |
| Gate semantics | D9: soft gate, fail-open, at-most-once via `stop_hook_active` |
| Prompting parity | D10 |
| Python runtime floor | D11: 3.9 + early probe + exact remediation; no-bootstrap install test |
