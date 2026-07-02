# Feature Specification: Proactive Code Guardrails

**Feature Branch**: `457-proactive-code-guardrails`

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "Help me improve the focus of this repository to ensure we are proactive at writing effective code and avoiding common vibe coding mistakes or antipatterns" — accompanied by a research report cataloguing AI-generated code failure modes (architectural drift, orphan state, swallowed async errors, superficial error handling, injection/auth/secret vulnerabilities, dependency hallucination, feedback-loop security degradation, context-window decay) and a seven-pass audit rubric (P0–P6; the source report labels it "six passes" but enumerates seven) with severity classification.

## Clarifications

### Session 2026-07-01

- Q: How should the write-time anti-pattern guardrails be enforced when an agent is writing code? → A: Guidance + automated advisory checks — prevention rules in deployed guidance plus non-blocking automated feedback (extending the existing auto-triggered quality feedback); Tier 1 gates retain exclusive blocking power.
- Q: How should the on-demand AI-code audit capability (the seven-pass rubric, P0–P6) be delivered? → A: One new dedicated user-invocable audit skill implementing the ordered passes; it reads the shared anti-pattern registry and shares the severity vocabulary. Existing skills keep their current scopes.
- Q: Which languages should the seeded registry's detection cues target at launch? → A: Language-agnostic category rules plus concrete detection cues for the toolkit's supported language set (shell, Python, JS/TS, Go, Terraform), matching existing refactor/verify coverage.
- Q: How rigorously should audit findings be verified before reporting? → A: Audit passes run single-agent; Critical and High findings receive independent cross-verification before being reported as verified. Medium and below rely on the evidence-trace requirement. Findings failing cross-verification are reported as unverified observations or dropped.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Write-Time Anti-Pattern Prevention (Priority: P1)

A developer (or an AI coding agent operating under this toolkit's deployed guidance) starts a coding task in any project. Before and during code writing, the agent has access to a concise, curated set of anti-pattern prevention rules — the documented failure modes of AI-generated code (swallowed errors, orphan state, hardcoded secrets, cosmetic abstractions, refactoring avoidance, dependency hallucination, etc.) — expressed as positive "do this instead" rules. The code produced avoids these defects at generation time rather than relying on after-the-fact review to catch them.

**Why this priority**: Prevention is the whole point of the request ("proactive at writing effective code"). Research cited by the user shows defects compound under iteration (37.6% vulnerability increase over five refinement cycles), so stopping them at write time delivers the most value per unit of effort. Every other story builds on the curated rule set this story creates.

**Independent Test**: Can be fully tested by giving an agent a representative coding task (e.g., an async data-fetch function with error handling) under the deployed guidance and verifying the output does not exhibit the registry's top anti-patterns (e.g., no catch-log-return-undefined, no unvalidated inputs at boundaries, no hardcoded secrets).

**Acceptance Scenarios**:

1. **Given** the guardrail rules are deployed, **When** an agent writes new code involving error handling, async operations, or secrets, **Then** the output follows the corresponding prevention rules (errors propagate a usable signal, async operations have handlers, secrets load from environment/secret stores).
2. **Given** the guardrail rules are deployed, **When** an agent iteratively refines existing code, **Then** existing security controls and validation logic are not removed or weakened without an explicit, stated reason.
3. **Given** the auto-loaded guidance context budget is at its enforced limit, **When** the guardrail rules are added, **Then** the total auto-loaded context remains within the enforced budget (rules are summarized in auto-loaded guides; full detail loads on demand).

---

### User Story 2 - On-Demand AI-Code Audit (Priority: P2)

A user asks for an audit of a codebase (their own project or a third-party one) suspected of carrying AI-generation defects. The toolkit runs a structured, ordered multi-pass review — orientation/inventory, architectural integrity, async logic and state lifecycle, security vulnerabilities, logic/business-rule integrity, quality/maintainability, and iterative-regression checks — and returns findings classified by severity (Critical → Informational) with a required action per severity and concrete evidence (file and line) for every finding.

**Why this priority**: Prevention (P1) covers new code; existing codebases already contain latent defects that "look correct." A repeatable audit converts the user-supplied rubric into an executable capability, and it is independently valuable even if no new code is ever written.

**Independent Test**: Can be fully tested by running the audit against a small fixture codebase seeded with known anti-patterns (a swallowed async error, a hardcoded credential, a dead module, an interface with one implementation) and verifying each seeded defect is found, correctly classified, and evidenced, with no findings fabricated for clean files.

**Acceptance Scenarios**:

1. **Given** a codebase with seeded anti-patterns, **When** the audit runs, **Then** every seeded defect appears in the findings with the correct severity class and a file/line citation.
2. **Given** a clean, well-structured codebase, **When** the audit runs, **Then** the audit reports no Critical or High findings and does not invent defects to appear thorough.
3. **Given** audit findings are produced, **When** they are reported, **Then** each finding includes the evidence trace (what was followed: the catch block's resolution, the auth check's resource-level enforcement, the dependency's registry existence) rather than surface-level pattern matches.

---

### User Story 3 - Anti-Pattern Learning Loop (Priority: P3)

When a review, lint failure, or audit in any session surfaces an anti-pattern instance ("bug déjà vu" — the same class of mistake recurring across sessions), the toolkit records it in the shared anti-pattern knowledge base so future sessions are warned about it proactively. The registry is maintainable: new anti-patterns can be added, and stale or over-triggering rules retired, without restructuring the toolkit.

**Why this priority**: The cited research identifies lack of persistent memory as the root cause of recurring AI mistakes. This story closes the loop between detection (P2) and prevention (P1), but it depends on both existing first and extends an existing capture mechanism rather than creating new value on its own.

**Independent Test**: Can be tested by recording a new anti-pattern entry, then verifying a subsequent session's write-time guidance and audit passes both incorporate it.

**Acceptance Scenarios**:

1. **Given** an anti-pattern instance is confirmed during review or audit, **When** it is captured, **Then** it is stored in the shared knowledge base with category, detection cue, prevention rule, and severity.
2. **Given** a newly captured anti-pattern, **When** a later session performs a related coding task or audit, **Then** the new entry participates in both prevention guidance and audit checks.

---

### Edge Cases

- What happens when a prevention rule conflicts with an explicit user instruction (e.g., user asks for a quick prototype with hardcoded values)? The user's explicit instruction wins; the agent notes the deviation and its risk in its response rather than silently complying or refusing.
- What happens when the rule set grows beyond what auto-loaded guidance can hold? Auto-loaded guides carry only the summary/index; full rule detail lives in on-demand references. The enforced context budget test remains the backstop.
- How does the audit behave on a codebase in a language or framework the rubric's examples don't cover? Category-level checks (error propagation, secrets, dead code, duplication) apply universally; language-specific detection cues degrade gracefully to manual-trace guidance instead of failing.
- What happens when an audit pass produces a plausible-but-wrong finding? Findings must carry evidence traces; Critical/High findings additionally undergo independent cross-verification before reporting. Findings that cannot be evidenced at a concrete location, or that fail cross-verification, are reported as "unverified observations," not defects.
- How does this avoid duplicating existing quality tooling (existing code-quality auto-trigger, antipattern detection on lint failures, refactor roadmaps, security review skills)? New capability must integrate with or extend those assets — one registry, shared severity vocabulary — not create a parallel overlapping system.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The toolkit MUST maintain a curated anti-pattern registry organized by category — architectural/structural (`arch`), async & state management (`async-state`), error handling (`error-handling`), security (`security`: injection, auth, secrets, data handling), dependency/supply-chain (`dependency`), and iteration/process (`iteration`: defects introduced by refinement cycles and cross-session drift); the parenthesized identifiers are the canonical tag strings used in the registry — where each entry has a name, description, detection cue, prevention rule ("do this instead"), and severity. Quality/maintainability defects (duplication, complexity) are registered under architectural/structural; quality/maintainability remains a dedicated audit pass.
- **FR-002**: The registry MUST seed from the user-supplied research: at minimum the ten documented structural anti-patterns, the async/orphan-state failure modes, the superficial-error-handling patterns, the security vulnerability classes (injection, IDOR/auth, hardcoded secrets, weak crypto, permissive CORS), the dependency risks (hallucinated packages, stale pins), and the iteration-specific risks (security-control removal during refinement, context-decay drift). Seeded entries carry language-agnostic category rules plus concrete detection cues for the toolkit's supported language set (shell, Python, JS/TS, Go, Terraform).
- **FR-003**: Write-time prevention guidance derived from the registry MUST be available to agents in all deployed assistant environments, with the auto-loaded portion staying within the repository's enforced context budget and full detail available on demand.
- **FR-004**: The toolkit MUST provide the on-demand audit as a single new dedicated, user-invocable capability that executes ordered passes (inventory/orientation, architectural integrity, async & state lifecycle, security, logic/business-rule integrity, quality/maintainability, iterative regression) against a target codebase; existing skills retain their current scopes.
- **FR-005**: Every audit finding MUST include a severity class (Critical, High, Medium, Low, Informational), the required action for that class, and concrete evidence (location plus the trace that confirms the defect); findings without evidence MUST be labeled as unverified.
- **FR-006**: The severity classes and required actions MUST align with the toolkit's existing validation tiers and verdict vocabulary (blocking vs. advisory) so audit output plugs into existing consensus/validation flows without a second severity scheme.
- **FR-007**: Confirmed anti-pattern instances observed during reviews, lint analysis, or audits MUST be capturable into the shared registry, and captured entries MUST participate in both future prevention guidance and future audits.
- **FR-008**: The feature MUST extend or integrate with existing quality assets (auto-triggered code-quality feedback, lint-failure anti-pattern detection, refactor roadmaps, security review skills) rather than duplicating them; there is one registry and one severity vocabulary.
- **FR-009**: Prevention rules MUST be phrased as actionable positive guidance an agent can apply while writing (e.g., "propagate a usable error signal from every catch"), not merely as descriptions of what bad output looks like.
- **FR-010**: Iterative-refinement safety MUST be explicit in the guidance: when modifying existing code, agents are directed to preserve existing security controls and validation logic unless the change is intentional and stated.
- **FR-011**: In addition to written guidance, the toolkit MUST provide automated, non-blocking advisory feedback that flags registry anti-patterns while code is being written or reviewed, by extending the existing auto-triggered quality feedback mechanism; these checks MUST NOT block the user's workflow (blocking remains exclusive to existing Tier 1 validation gates).
- **FR-012**: Critical and High audit findings MUST pass an independent cross-verification (adversarial re-check of the evidence) before being reported as verified; findings that fail cross-verification are downgraded to unverified observations or dropped. Medium and lower findings rely on the evidence-trace requirement (FR-005) alone.

### Key Entities

- **Anti-Pattern Registry Entry**: One named failure mode; attributes: category, description, detection cue, prevention rule, severity, provenance (seeded from research vs. captured from a session).
- **Audit Pass**: One ordered stage of the audit rubric; attributes: objective, checks performed, evidence requirements; passes execute in a defined sequence because later passes rely on earlier orientation.
- **Finding**: One evidenced defect from an audit; attributes: anti-pattern reference, severity, required action, location, evidence trace, verified/unverified status.
- **Severity Class**: Shared vocabulary mapping defect impact to required action, aligned with the existing blocking/advisory validation tiers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The deployed registry covers 100% of the anti-pattern categories named in the source research (6 categories) and at least 25 individual named anti-patterns at launch.
- **SC-002**: On a seeded-fixture audit, at least 90% of planted anti-pattern instances are detected with correct severity, and zero defects are fabricated for clean files.
- **SC-003**: On representative coding tasks performed under the deployed guidance, the top write-time anti-patterns (swallowed errors, missing boundary validation, hardcoded secrets, missing async handlers) appear in 0 of the produced outputs during acceptance testing.
- **SC-004**: The auto-loaded guidance additions keep every assistant's startup context within the repository's enforced context budget (existing budget test still passes).
- **SC-005**: A newly captured anti-pattern becomes active in both prevention guidance and audit checks in the next session with no restructuring work (capture-to-active in one step).
- **SC-006**: An audit of a small project (≤50 source files) completes and reports severity-classified, evidenced findings in a single invocation without manual orchestration by the user.

## Assumptions

- "This repository" means the Manifest toolkit itself: the deliverable is guidance, registry content, and skills deployed to all assistant homes — not a one-off audit of a specific application codebase (the "NextToken" name in the pasted report is an artifact of the source research, not a target here).
- The pasted meta-prompt-engineering framing and research report are source material describing *what* to guard against; the user wants their substance encoded into the toolkit, not a literal reproduction of the report or a meta-prompt system.
- The existing shared knowledge base and its capture mechanism are the natural home for the registry; this feature curates and seeds it rather than inventing a parallel store.
- Prevention rules are language-agnostic at the category level; concrete detection cues target the toolkit's supported language set (shell, Python, JS/TS, Go, Terraform). Other languages degrade gracefully to the category-level rules.
- The audit capability targets local codebases accessible to the session; auditing remote/third-party code is done by checking it out first (out of scope to fetch).
- Enforcement remains advisory-first, consistent with the toolkit's existing non-blocking philosophy (auto-triggered feedback does not block the user's flow); hard blocking stays reserved for the existing Tier 1 validation gates.
- Externally cited statistics (occurrence rates, degradation percentages) inform prioritization only; they are not requirements to reproduce or verify.
