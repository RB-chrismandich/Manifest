# Goal Compose: research-to-plan validation

Date: 2026-09-08
Verdict: Documentation chain reviewed; no remaining material inconsistency
identified after corrections. Implementation and model/runtime E2E tests are NOT RUN.

## Artifacts

- [Research ledger](2026-09-08-goal-creation-research.md)
- [Revised design](../design/specs/2026-09-08-goal-compose-design.md)
- [Implementation plan](../design/plans/2026-09-08-goal-compose.md)

## Scope and evidence

Checked source attribution and applicability, repository ownership and isolation,
contract field consistency, user authority, save behavior, host capability limits,
all FR-01 through FR-10 mappings, and pilot acceptance requirements. The plan has
five dependent implementation tasks and 25 unchecked steps. These checkboxes
describe future work; none is a claim of implemented functionality.

Reopened ten sources: OpenAI Academy, Anthropic prompting and agent evaluations,
SELFGOAL, Reflexion, the Codex Reddit completion report, Plan-and-Solve,
Self-Refine, Anthropic context engineering, and the Claude Reddit workflow thread.
Other ledger rows retain explicitly labeled prior-turn inspection provenance.
The evidence supports the design rationale but does not prove local efficacy.

Inspected current planning and checkpoint skills, capability manifests, plugin
view generator, isolated runtime tests, and frozen workflow-fixture conventions.
Confirmed Python >=3.11 in both project pyproject files. The new feature files
and tests have not been created or executed.

## Findings and disposition

| Finding | Correction | Verification |
|---|---|---|
| Original research answer implied exhaustive coverage | Ledger explicitly bounds the search and separates anecdotes from controlled evidence | Source/claim review |
| No readiness verdict for inadequate but repairable goals | Added NEEDS_REVISION to design and T3 | Vocabulary cross-check |
| Atomic persistence had no owning component | Added save_goal.py, exact save semantics and T2 fault/race tests | Design-to-task mapping |
| Contract fields and coverage shapes were unspecified | Defined version-1 fixture, field types, tagged evidence, budgets and obligations | JSON example parsed successfully |
| Activation did not resolve missing active-state visibility | Block mutation when conflicting-goal absence cannot be established | T3 decision table |
| Exclusions could not be referenced by constraints | ID-addressable exclusion records and a positive coverage fixture | Independent review and follow-up |
| Revision alone could not detect same-revision rewrites | Accepted snapshot/path/revision/digest and five negative handoff cases | Independent review and follow-up |

The configured spec-review command was attempted with explicit research, design,
and plan paths. It exited 1 before a review: sandbox denied the review CLI's
home log/crash writes and localhost listener. This was not a review verdict or
an auto-approval rejection. No permission settings were changed.

Fallback: an independent in-session reviewer inspected the three artifacts and
related repository interfaces. It reported the two final findings above; after
correction it re-read the affected sections and found both resolved, with no
remaining material gap in those reviewed portions. The reviewer did not reopen
external sources; source verification was performed by the primary agent.
This was an independent agent pass, not a cross-vendor review.

## Requirement coverage

| Requirement | Plan owner | Required future proof |
|---|---|---|
| FR-01 requirement fidelity | T1/T3 | Semantic source coverage |
| FR-02 profile fidelity | T3 | Three-profile trace comparison |
| FR-03 structural rejection | T1 | Validator positive/negative tests |
| FR-04 readiness integrity | T1/T3 | Inadequate valid JSON cannot become READY |
| FR-05 no accidental execution | T1/T3 | Tool traces and filesystem checks |
| FR-06 capability-aware activation | T3/T5 | Decision fixtures plus real host observations |
| FR-07 missing evidence | T3/T5 | Missing context/metric/tool scenarios |
| FR-08 persistence integrity | T2 | No-clobber, atomicity and fault tests |
| FR-09 isolated delivery | T4 | Installed assets and generator checks |
| FR-10 scope through handoff | T3/T4 | Snapshot/digest comparisons and semantic change review |

## Mechanical checks and remaining gates

Document checks parsed the embedded JSON, verified all ten FR IDs appear in the
plan, found T1–T5 and 25 unchecked steps, checked local Markdown links, and checked
balanced fenced blocks. These checks establish document structure only; semantic
review supplies the cross-artifact interpretation.

Remaining gates are implementation tests, installed-bundle validation, actual
model/host behavior, and the 144-trial paired pilot (12 scenarios × 2 conditions
× 2 models × 3 repeats). Missing trial evidence blocks release readiness; it does
not make this documentation deliverable incomplete. No feature efficacy,
production readiness, native-host support matrix, or successful runtime E2E
result is claimed by this review.
