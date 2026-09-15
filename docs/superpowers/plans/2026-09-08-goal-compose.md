# Goal Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:subagent-driven-development only when delegated execution is selected. Steps use checkbox syntax for tracking.

**Goal:** Deliver an opt-in goal composition skill with faithful model profiles, honest validation, explicit activation, and measured end-to-end behavior.

**Architecture:** One planning-bundle skill owns semantic composition and host-tool activation. Standard-library helpers validate inert JSON and persist explicitly requested artifacts. Existing plan, delegation, and checkpoint interfaces retain execution ownership.

**Tech Stack:** Python standard library, pytest, JSON, Markdown, existing plugin generators and evaluation conventions. No new runtime dependencies.

**Spec:** [Goal composition design](../specs/2026-09-08-goal-compose-design.md)

**Research:** [Evidence ledger](../../research/2026-09-08-goal-creation-research.md)

**Status:** Written and reviewed as a plan; every implementation checkbox remains open. A documentation review is not an implemented-feature E2E pass.

## Global constraints

- Limit input to 1 MiB; schema version 1; reject unknown fields, duplicate keys, non-finite numbers, and boolean integers.
- No new mandatory MCP, model API package, hook, or service. Target Python 3.11 or newer, matching the current project floor (`requires-python = ">=3.11"` in `pyproject.toml`). CI (`.github/workflows/ci.yml`) only provisions Python 3.14, so a passing CI run verifies 3.14 only; avoid 3.12+-only syntax so 3.11 compatibility holds by construction, and do not claim CI proves the 3.11 floor.
- Draft and validate never execute proposed evidence commands or activate goals. Native activation requires current authorization and observable goal state.
- JSON is authoritative; Markdown is derived. Use explicit destinations, private atomic writes, and no implicit overwrite or global goal store.
- Preserve dirty-tree work. Do not publish, commit, start paid model trials, or implement this feature merely because this plan was requested. At execution time, commits follow the repository verification workflow and existing authorization.

## File ownership and dependencies

`B` below means `plugins/manifest-spec-planning/skills/goal-compose`; it is a documentation abbreviation, not a shell variable or a second source root.

| Unit | Files | Responsibility |
|---|---|---|
| Contract | `B/references/goal-contract.md`, `B/scripts/validate_goal.py` | Exact schema and pure validation |
| Persistence | `B/scripts/save_goal.py` | Explicit no-clobber or authorized-replacement saves |
| Skill | `B/SKILL.md`, `B/agents/openai.yaml`, `B/references/{codex-profile,claude-profile,examples}.md` | Composition, readiness, rendering and host activation |
| Tests | `tests/python/plugin_runtime/test_goal_{contract,storage,integration}.py`, `tests/fixtures/goal_compose/` | Deterministic and isolation coverage |
| Evaluation | `B/evals/{evals.json,protocol.md}`, `tests/fixtures/goal_compose/pilot/` | Semantic traces and paired end-to-end pilot |

Dependencies: T1 → T2 and T3; T2 + T3 → T4; T4 → T5. Execute sequentially unless a later approved execution strategy isolates independent edits.

## Exact version-1 data contract

The following complete small contract is the positive fixture, saved during T1
as `tests/fixtures/goal_compose/valid.json`:

```json
{
  "schema_version": 1,
  "revision": 1,
  "source_request": "Fix sorting in src/sort.py; preserve the public API.",
  "outcome": "Sorting produces ascending results while preserving the public API.",
  "requirements": [
    {"id": "R1", "text": "Return ascending results", "kind": "result", "provenance": "explicit", "coverage": ["C1"]},
    {"id": "R2", "text": "Preserve the public API", "kind": "constraint", "provenance": "explicit", "coverage": ["B1"]}
  ],
  "context": [
    {"id": "S1", "reference": "src/sort.py", "relevance": "Implementation", "status": "observed"}
  ],
  "boundaries": {
    "in_scope": ["Repair sorting"],
    "exclusions": [{"id": "B2", "text": "Unrelated cleanup"}],
    "preserved": [{"id": "B1", "text": "Public function names and signatures"}],
    "approval_required": []
  },
  "criteria": [
    {"id": "C1", "requirement_ids": ["R1"], "expected": "Existing sorting tests and unsorted-input regression pass", "evidence": {"method": "command", "reference": "python3 -m pytest tests/test_sort.py", "cwd": "."}}
  ],
  "output_obligations": [],
  "optional_improvements": [],
  "operating_contract": {
    "revalidation": "Inspect current code and tests before editing.",
    "adaptation": "Change the approach without dropping requested behavior.",
    "escalation": "Report a missing environment or material decision.",
    "stopping": "Finish only with evidence for all criteria.",
    "continuation": "Revalidate state and retain existing live-operation handles."
  },
  "assumptions": [],
  "open_questions": []
}
```

All object fields above are required except optional `token_budget` at root and
method-specific evidence fields. `token_budget` and `revision` are positive exact
integers; `schema_version` is exactly integer 1. Strings are nonblank. Empty lists
are permitted except `requirements`, `criteria`, `boundaries.in_scope`, and
`requirement_ids`/`coverage`. Each root and nested object accepts only listed keys.

Requirements use `kind=result|constraint|output` and
`provenance=explicit|inferred`. Output obligations and optional improvements are
arrays of `{id,text}`. `preserved`, `exclusions`, and `approval_required` contain `{id,text}`;
`in_scope` contains strings. Assumptions and open questions contain
strings. IDs match `[A-Z][A-Z0-9_-]*` and are globally unique. Coverage targets
must be criterion IDs, preserved/exclusion/approval boundary IDs, or output-obligation IDs;
optional improvements cannot satisfy mandatory coverage. Every result requirement
links to at least one criterion that reciprocally names it; every criterion's
requirement IDs must exist and link back. A constraint or output may map directly
to a boundary or output obligation. Do not infer semantic sufficiency from links.

Evidence is one of these exact tagged objects:

```text
command:      {method, reference, cwd}
artifact:     {method, reference, content}
environment:  {method, reference, state}
human_review: {method, reference, rubric, decision}
```

All fields are strings. `reference` names the command, artifact, system, or reviewer
role. Context status is `observed|unverified`; that status is an attributed claim
and is rechecked where consequential. Contracts contain no approved/readiness
field. Material scope inferred by the agent requires explicit agreement before
READY; nonmaterial assumptions remain visible.

## T1: Contract validation and diagnostic CLI

**Files:** Create `B/references/goal-contract.md`, `B/scripts/validate_goal.py`,
`tests/fixtures/goal_compose/valid.json`, and
`tests/python/plugin_runtime/test_goal_contract.py`.

**Interfaces:** `load_contract(stream: BinaryIO) -> dict`,
`validate_contract(value: object) -> list[dict[str,str]]`,
`main(argv: list[str] | None = None) -> int`.
Diagnostics have exactly `code`, `path`, and `message`; use structural field paths,
not raw unknown keys or input values. `GoalInputError` carries `code` and exit code.
CLI accepts `--input FILE|- --format json|text`; default input is stdin and format
is JSON. Always emit `{status,diagnostics}` semantics; status is VALID, INVALID, or
ERROR (matching the design's validator status vocabulary). `--format text` renders
the same status/diagnostics as one `STATUS` line followed by one
`<code> <path>: <message>` line per diagnostic (no lines beyond the status line
when diagnostics is empty); exit codes are identical across both formats.
Exit 0/2/3 means valid/invalid/operational error. `--help` exits 0 without reading.

- [ ] Write the positive fixture above and parameterized negative cases. Include exact-limit and one-byte-over input, malformed UTF-8/JSON, duplicate keys, NaN/Infinity, booleans, deep nesting, missing keys, unknown keys, dangling and duplicate IDs, wrong evidence variant, and invalid reciprocal coverage.
  Include a positive constraint-only coverage case: append explicit constraint R3, “No unrelated cleanup,” with coverage `["B2"]`; this must validate without duplicating a criterion.
- [ ] Run `uv run --project configs/claude pytest tests/python/plugin_runtime/test_goal_contract.py -q`; confirm the feature module is missing before adding it. An environment/bootstrap failure is not the intended red result.
- [ ] Implement bounded reading with `stream.read(1048577)`, UTF-8 decoding, duplicate-key rejection using `object_pairs_hook`, non-finite rejection through `parse_constant`, and explicit typed validation. Catch recursion/parser errors as INVALID and read errors as ERROR. Validate IDs before adding them to lookup tables; cap diagnostics to 50 with a final truncation diagnostic.
- [ ] Add subprocess tests proving evidence strings are inert and errors remain valid JSON without echoing synthetic sensitive values. Use the test below as the core behavioral assertion, loading the fixture rather than inventing a second schema.

```python
def test_boolean_version_is_invalid(goal_module, valid_contract):
    valid_contract["schema_version"] = True
    findings = goal_module.validate_contract(valid_contract)
    assert any(f["path"] == "$.schema_version" for f in findings)

def test_missing_reciprocal_link_is_invalid(goal_module, valid_contract):
    valid_contract["criteria"][0]["requirement_ids"] = ["R2"]
    assert goal_module.validate_contract(valid_contract)
```

- [ ] Re-run the targeted suite, then inspect all error branches for honest status propagation. T1 covers FR-03 and the deterministic half of FR-04; it cannot prove semantic readiness.

## T2: Explicit artifact persistence

**Files:** Create `B/scripts/save_goal.py` and
`tests/python/plugin_runtime/test_goal_storage.py`; extend the contract reference
with save behavior.

**Interfaces:** `save_bytes(destination: Path, payload: bytes, replace: bool=False) -> None`;
CLI `--input FILE|- --output FILE --kind json|markdown [--replace]`.
JSON input is validated through sibling `validate_goal`; Markdown input must be
bounded valid UTF-8. No directory creation. Reject final symlinks and nonregular
existing files. Canonicalize the existing parent directory and print its resolved
destination so the user can see where the explicit save occurred. `--replace`
is supplied only from current user authorization, never from contract content.
Emit `{status,path,diagnostics}`; 0 SAVED, 2 INVALID/CONFLICT, 3 ERROR.

- [ ] Write tests for no-clobber, private mode, partial-write failure, absent parent, symlink target, existing destination directory, JSON validation failure, and a race creating the destination between precheck and install.
- [ ] Run `uv run --project configs/claude pytest tests/python/plugin_runtime/test_goal_storage.py -q` and confirm intended failure.
- [ ] Implement a sibling temporary file with `tempfile.mkstemp(dir=parent)`, mode 0600, complete write, flush and fsync. For no-clobber use `os.link(temp,destination)` so a racing existing destination yields conflict. For authorized replacement use `os.replace`; always clean the temporary path in `finally`. Do not fall back to non-atomic copying if the filesystem rejects linking.
- [ ] Validate the behavior with these tests and injected I/O exceptions; ensure replacement failures preserve existing bytes and messages do not include payload content.

```python
def test_no_clobber(storage_module, tmp_path):
    path = tmp_path / "goal.json"
    path.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        storage_module.save_bytes(path, b"new")
    assert path.read_bytes() == b"original"
```

- [ ] Run T1 and T2 suites together. Document that JSON and Markdown are independently atomic; a failed Markdown save does not erase successful JSON. T2 covers FR-08. Atomic namespace replacement does not promise survival of power loss on every filesystem.

## T3: Composition, profiles, readiness and activation skill

**Files:** Create `B/SKILL.md`, `B/references/codex-profile.md`,
`B/references/claude-profile.md`, `B/references/examples.md`, and
`B/evals/evals.json`. `B/agents/openai.yaml` is a T4-generated output of
`tools/generate_plugin_views.py` (writes it per discovered skill); do not
hand-author it here — verify it after T4's generator run.

**Interfaces:** Skill verbs and target arguments are exactly those in the design.
`validate` loads JSON, runs T1, then performs semantic review without executing
evidence commands. For prose input, disclose extraction before reviewing it.
Draft sends contract JSON through stdin for structural validation; save only via
T2 when requested. Rendering is agent-owned and tested semantically, not a new
template engine. Every rendering preserves all IDs and requirement text needed
for downstream work. Host-only commentary stays outside the portable goal.

- [ ] Write fixtures with exact source request, expected requirement IDs/text, expected readiness, permitted tool calls and forbidden effects. Use READY, NEEDS_INPUT, BLOCKED, NEEDS_REVISION exactly; invalid structure always requires revision, with any external blockers reported alongside it.
- [ ] Exercise these fixtures against a baseline without the skill when a model evaluation environment is authorized; otherwise record NOT RUN and retain the fixtures. Do not mistake static phrase assertions for model behavior.
- [ ] Write the skill flow: extract → inspect → compose → structural validation → semantic review → render. Repair locally resolvable inadequacy once per new finding; ask one material decision if needed. Maintain the original request and explicit/inferred distinction. Add examples for bug fix, human-reviewed UI quality, and unavailable evidence.
- [ ] Write the activation decision table below verbatim in behavior, adapting actual tool names only after inspecting current host metadata. No universal native CLI is introduced.

| Situation | Required action/result |
|---|---|
| Draft or validate | No create/update/execute call |
| Activate and readiness not READY | Return readiness findings; no mutation |
| Activate but native creation absent | UNSUPPORTED plus copyable goal |
| Native creation exists but active state cannot be inspected | BLOCKED; no mutation |
| Different unfinished goal exists | NEEDS_INPUT; preserve it |
| Same rendered objective already active | ALREADY_ACTIVE; no duplicate call |
| No conflicting goal, explicit authorization, READY | Create once; include budget only if explicitly supplied |
| Success with read-back available | Compare objective and report ACTIVATED only on match |
| Success without read-back | Report creation acknowledged, not independently confirmed |
| Error or ambiguous response | Report ERROR/UNKNOWN; inspect before retry, never blind retry |

- [ ] Inspect model-run traces for each profile and activation scenario. Record exact model and host versions, fixture identity, diagnostics and observed tools. T3 supplies FR-01, FR-02, FR-04–FR-07 and FR-10; these remain unverified if only fixtures exist.

## T4: Existing consumers and standalone distribution

**Files:** Modify
`plugins/manifest-spec-planning/skills/plan-manage/SKILL.md`,
`plugins/manifest-spec-planning/skills/spec-audit-tasks/SKILL.md`,
`plugins/manifest-spec-planning/manifest-capabilities.yml`,
`configs/claude/config/skill_policies.yml` (registry entry plus
`domain_expected_total`/`policy_expected_total`/`expected_total` count bumps —
required by `tests/bats/bundle_partition.bats`), and
`configs/claude/config/command_config.yml` (`tool_policies` entry with a
`subagents` disposition — required by `tests/bats/subagent_policy.bats`);
create `tests/python/plugin_runtime/test_goal_integration.py`.
Generated outputs are emitted by existing generators, not edited by hand.

**Interfaces:** Consumers receive explicit contract path/revision and rendered text
through existing skill arguments or contextual input; do not add undocumented
CLI flags. Plan records stable requirement-to-task links. Audit compares tasks
and evidence back to the supplied contract. Optional Delegate handoff uses its
qualified skill and preserves its existing result envelope. Checkpoint handoff
uses `manifest-workspace:session-checkpoint` and includes revalidation; neither
consumer is imported through a sibling runtime path.

Carry `{contract_path, revision, sha256}` in the existing plan/handoff artifact,
alongside an accepted contract snapshot. Compute SHA-256 from exact accepted JSON
bytes, not rendered Markdown. Before consuming a path, compare its bytes and
revision to that baseline. Missing baseline means unverified, not accepted.
A digest detects stale content; authorization comes from the actual user/session.
The accepted snapshot allows comparison of deleted or weakened requirements,
boundaries (exclusions, preserved behavior, approval-required actions), and
output obligations even when a revision increments. Keep it in the existing handoff, without
a new approval database. Consumers use standard-library hashing in their current
execution context; no new public CLI is required.

- [ ] Add isolated-copy tests using the existing `test_spec_planning_runtime.py` pattern: run helpers from a copied bundle with a temporary HOME/XDG environment, empty PYTHONPATH, `python -S -B`, no project imports and no installed sibling plugins. Verify nested assets ship.
  Add five handoff fixtures: changed bytes at the same revision; lower revision than accepted; deleted mandatory requirement at a higher revision; weakened evidence, boundary, or output obligation at a higher revision; checkpoint pointing to an old digest. Byte/revision comparison detects cases one, two and five; semantic model traces must flag deletion and weakening of requirements, boundaries, and output obligations against the accepted snapshot. None may silently inherit READY. A positive authorized-revision fixture recomputes readiness and replaces the accepted snapshot only after agreement.
- [ ] Run `uv run --project configs/claude pytest tests/python/plugin_runtime/test_goal_integration.py -q`; confirm intended missing-skill failure.
- [ ] Add optional contract intake to Plan Management and Task Completion Audit. Absence preserves current behavior. Presence causes validation and revision checking before consumption. Goal drafting never calls plan execute, Delegate task, or checkpoint automatically. Explicit handoff keeps the user’s existing scope.
- [ ] Bump `plugins/manifest-spec-planning/.claude-plugin/plugin.json` to the next
  minor version (skill added, per `docs/PLUGIN_RELEASE.md`'s bump table) and bump
  every other domain bundle's `plugin.json` to the same version in lockstep, since
  `tools/build_manifest_release.py` (`_release_version`) requires all domain bundle
  versions to be identical and fails the release build otherwise. Update the
  matching marketplace entries and regenerate views after bumping.
- [ ] Regenerate views with `uv run python tools/generate_plugin_views.py`, mirror with `bash configs/claude/scripts/generate_skill_mirror.sh`, and harness rules through the existing `generate_cursor_rules.sh`. Read `generate_commands_doc.py --help` before selecting its documented regeneration mode. Inventory generator diffs against the dirty-tree baseline and preserve unrelated edits. Refresh capability inspection using the existing release inspection path; do not hand-mark new capability rows READY.
- [ ] Run the commands below and review installed output. Keep the existing exact runtime-asset-set test unchanged: nested skill scripts should ship with the skill, not become undeclared root runtimes. T4 covers FR-09 and handoff FR-10.

```bash
uv run --project configs/claude pytest tests/python/plugin_runtime/test_goal_contract.py tests/python/plugin_runtime/test_goal_storage.py tests/python/plugin_runtime/test_goal_integration.py tests/python/plugin_runtime/test_spec_planning_runtime.py -q
uv run python tools/generate_plugin_views.py --check
git diff --check
```

## T5: Paired pilot and acceptance evidence

**Files:** Create `B/evals/protocol.md`,
`tests/fixtures/goal_compose/pilot/manifest.json`, per-scenario request/rubric files,
and `docs/research/2026-09-08-goal-compose-pilot.md` when actual trials begin.
Do not overwrite any existing frozen benchmark fixtures from other workstreams.

**Interfaces:** Reuse existing evaluation runner capabilities only after verifying
they can execute and record the protocol; a runner name is not proof of coverage.
If they cannot, manual bounded native sessions are acceptable with complete records.
No new provider service is required. Trial records contain scenario, condition,
model, host/version, repeat index, input digest, environment digest, outcome,
requirement coverage, sufficiency judgment, authority violation, completion claim,
tokens/cost or null, elapsed seconds, corrections, and evidence paths.

- [ ] Freeze twelve scenarios: sort bug; API-preserving migration; performance with baseline; performance without baseline; subjective UI; cited research; ambiguous product scope; forbidden mutation; inaccessible context; contradictory constraints; active conflicting goal; interrupted operation. Each gets an independently authored rubric and expected allowed behavior. Human-review requirements may yield READY with a later human acceptance gate; missing metrics or unavailable verification yield NEEDS_INPUT/BLOCKED.
- [ ] Use 8 development scenarios and 4 held-out scenarios (subjective UI, inaccessible context, active conflicting goal, interrupted operation). Tune only on development data. Run the final frozen pilot across all twelve and report the held-out subset separately. Do not claim the tuned subset is unbiased evidence.
- [ ] After provider execution is authorized, run baseline and skill conditions on one available OpenAI model and one available Claude model, three repeats each: 12 × 2 × 2 × 3 = 144 trials. Each trial contains goal composition and, where authorized in a disposable fixture, downstream execution; ambiguity/blocker cases grade the correct stop. Record composition and execution costs separately. Hold all other instructions, tools, task state and budgets constant. Randomize condition order.
- [ ] Grade actual artifacts/environment and traces against frozen acceptance, with independent human review for sufficiency and qualitative outcomes. Report aggregate and per-scenario counts, denominators, failed and missing trials, paired differences and uncertainty. Do not infer activation safety from a fake host test alone: include actual host traces where supported and UNSUPPORTED coverage where not.
- [ ] Fill the release evidence table below. Release as opt-in only when every mandatory requirement is verified and the pilot is documented. Any authority violation or silent scope loss blocks release. Provider unavailability leaves the pilot BLOCKED, never waived. Default activation remains a separate decision requiring a preregistered benefit/cost criterion and sufficient evidence.

| Requirement | Implemented by | Evidence needed |
|---|---|---|
| FR-01 | T1, T3 | Source-to-requirement semantic fixture results |
| FR-02 | T3 | Generic/Codex/Claude trace comparison |
| FR-03 | T1 | Negative and positive validator suite |
| FR-04 | T1, T3 | Structurally valid but inadequate goal rejected by semantic review |
| FR-05 | T1, T3 | Draft/validate traces with no execution effects |
| FR-06 | T3, T5 | Host decision cases and live capability behavior |
| FR-07 | T3, T5 | Missing-source/metric/tool and human-review results |
| FR-08 | T2 | Atomic/no-clobber/failure tests |
| FR-09 | T4 | Installed-bundle isolation and generated views |
| FR-10 | T3, T4 | Revision, handoff and stale-state fixtures |

## Completion and handoff

Plan execution is complete only with implemented files, passing deterministic
checks, semantic trace results, and the documented pilot. A packaged experimental
candidate can exist before the pilot but cannot be called release-ready. Final
handoff states exactly which gates passed, failed, or were unavailable. Publication
and promotion are separate actions requiring the user's existing or new authority.

Estimated implementation effort: 2–3 engineer days for T1–T4; another 1–2 days
for pilot preparation and grading, plus provider runtime. This is a planning
estimate, not a model-runtime or cost guarantee.
