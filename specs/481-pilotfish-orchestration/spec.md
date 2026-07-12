# Feature Specification: Pilotfish-Style Cost-Tiered Model Orchestration

**Feature Branch**: `481-pilotfish-orchestration`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "Integrate pilotfish-style cost-tiered multi-model orchestration into Manifest. Pilotfish (https://github.com/Nanako0129/pilotfish, MIT) is a config-only orchestration layer for Claude Code that routes each unit of work to the cheapest capable model tier — keeping frontier models for planning/decision/review and delegating mechanical execution to cheaper tiers, gated behind a fresh-context verifier. Vendor its role-agents + delegation policy into Manifest's deployed config, deployed by bootstrap under a service toggle, reconciled with Manifest's model pins."

## Clarifications

### Session 2026-07-09

- Q: Does enabling pilotfish change the deployed main-session model (Layer-1 settings.json
  "best" alias + fallback chain), or only add role-agents + policy? → A: Agents + policy
  only — do NOT change the main-session model or `settings.json`. Deploy the role-agents and
  the delegation-policy reference; roles use Claude Code's built-in model aliases
  (haiku/sonnet/opus) so no model-alias definition file or settings change is deployed.
- Design correction (product spec-review, 2026-07-09): the earlier custom four-tier alias
  layer (best/high/mid/cheap) had no runtime resolution path — Claude Code agent frontmatter
  `model:` accepts only its built-in aliases (haiku/sonnet/opus), `inherit`, or a full model
  ID. Roles now bind to built-in aliases directly; those float to current versions (opus→Opus
  4.8, sonnet→Sonnet 5, haiku→Haiku 4.5), so pin reconciliation is automatic with no deployed
  alias file and no settings mutation.
- Q: Which delegated results must pass the fresh-context verifier? → A: Selective — gate
  mutating, judgment, and security work; skip pure read-only lookups (scout/Explore).
- Q: When a role-agent filename already exists in the deployed agents directory, how should
  deployment behave? → A: Abort the pilotfish deploy step with an error naming the colliding
  file, and leave the existing file untouched (touch nothing).
- Q: Which roles should Manifest vendor, incl. overriding the built-in search agent? → A:
  All six pilotfish roles (scout, Explore search-override, mech-executor, executor, verifier,
  security-executor), with the Explore search-override bound to the cheapest tier.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enable cost-tiered orchestration (Priority: P1)

A Manifest operator wants their Claude Code sessions to spend less on model usage
without losing output quality. They enable the pilotfish integration during setup.
The setup deploys a named set of role-agents and a delegation policy into their Claude
home. In the next session, the main (frontier) model plans and decides, but routes
mechanical and read-only work to cheaper tiers, and confirms results through an
independent verifier before proceeding.

**Why this priority**: This is the core value — measurable cost reduction with preserved
quality. Without it, nothing else in the feature matters. It is the MVP.

**Independent Test**: Enable the integration, confirm the role-agent definitions and the
delegation policy are present in the Claude home, run a representative multi-step task,
and observe that mechanical steps are delegated to cheaper tiers while planning/decision
stays on the frontier tier and results pass a verification step.

**Acceptance Scenarios**:

1. **Given** a fresh Manifest deployment with the integration enabled, **When** setup
   completes, **Then** the vendored role-agent set and the delegation policy are present
   in the deployed Claude home and are readable by a Claude Code session.
2. **Given** the integration is enabled, **When** the orchestrator handles a
   fully-specified mechanical task, **Then** it delegates that task to the cheapest
   capable role rather than the frontier tier.
3. **Given** a delegated result, **When** the orchestrator receives it, **Then** an
   independent fresh-context verifier confirms or refutes it before the orchestrator
   proceeds.

---

### User Story 2 - Re-tier a role in one edit (Priority: P2)

A maintainer wants a role to run on a cheaper (or richer) model. They edit that one role
file's `model:` alias — one line, one file — re-deploy, and that role follows; no policy
prose and no other role changes. Separately, when a model *version* is superseded, no edit
is needed at all: the built-in aliases (haiku/sonnet/opus) float to the current version
automatically.

**Why this priority**: Cheap, localized tuning is a primary reason to adopt named roles over
hard-coded model IDs. Valuable but subordinate to the feature existing at all.

**Independent Test**: Change one role file's `model:` alias, re-deploy, and confirm that role
now resolves to the new alias while unrelated roles and the policy text are unchanged.

**Acceptance Scenarios**:

1. **Given** a deployed role set, **When** a maintainer edits one role file's `model:` alias
   and re-deploys, **Then** only that role resolves to the new model and no other role or the
   policy prose changes.
2. **Given** a model version referenced by a built-in alias is superseded, **When** the
   orchestrator dispatches to a role using that alias, **Then** the alias resolves to the
   current version with no Manifest edit (Claude Code handles model availability).

---

### User Story 3 - Enable, then cleanly reverse (Priority: P3)

An operator tries the integration, then decides to turn it off. Disabling removes exactly
the pilotfish configuration and nothing else, leaving the rest of the Claude home intact,
and the repository's quality gates stay green throughout.

**Why this priority**: Safe opt-in with no lock-in lowers the barrier to trying the
feature and protects existing setups. Important for trust but not part of the core value
slice.

**Independent Test**: Enable the integration, capture the Claude home state, disable it,
and confirm the home is byte-identical to the pre-enable state (clean add/remove) with all
repository gates passing.

**Acceptance Scenarios**:

1. **Given** the integration was enabled, **When** the operator disables it and
   re-deploys, **Then** only the pilotfish role-agents and delegation-policy content are
   removed and the rest of the Claude home is unchanged.
2. **Given** the integration is enabled, **When** the repository's gate suite runs,
   **Then** all gates (naming taxonomy, context/budget, deploy reconcile/prune,
   derived-doc sync) pass.

---

### Edge Cases

- **Agent-directory collision (enable)**: a `~/.claude/agents/` that Manifest does not own
  (no marker) already holds a file whose name is one of the six pilotfish role files. Enable
  must detect this specific-name collision and abort, not overwrite. A user agent with a
  *different* name is not a collision and must not block enabling.
- **Re-run when already enabled**: enabling twice (or a routine `bootstrap.sh` re-run) over a
  Manifest-owned agents dir re-runs the copy + pointer-inject, which reconverge to the same
  tree — an idempotent no-op **in effect** (not a skip of the enable path, and not a collision;
  the marker distinguishes owned from foreign) — Principle V.
- **User agent added after enabling**: a user drops their own (differently-named) agent into
  `~/.claude/agents/` after the pilotfish deploy. Disabling must remove only the pilotfish files
  (manifest-scoped), keeping the user's agent and the directory; and a *subsequent re-enable
  must not deadlock* on that surviving user agent (the collision guard keys on the six role-file
  names, not any file). (`deploy_reconcile` scans only `skills`/`config` units, not `agents/`,
  so it never orphan-prunes agents either.)
- **Disabled deploy never clobbers a user agent**: because `agents/` is excluded from the
  wholesale rsync and the disable prune runs only when Manifest's marker is present, a default
  (disabled) `bootstrap.sh` run over a `~/.claude/agents/scout.md` the *user* authored leaves it
  byte-identical — Manifest never deploys its own marker or files on a disabled run.
- **Model unavailable at runtime**: the model a role's built-in alias resolves to is
  unavailable; Claude Code's own model-availability handling MUST degrade gracefully rather
  than erroring out (the policy documents this; Manifest deploys no custom fallback chain).
- **Budget pressure**: adding the delegation-policy pointer to the always-loaded orchestration
  guide risks pushing it over its context-budget cap. The **deployed** guide (source + injected
  pointer) is gated ≤ cap; room was reclaimed by condensing verbose guide content, not by
  raising the cap.
- **Toggle drift**: the recorded toggle state and the actually-deployed files disagree
  (e.g. enabled in config but files absent, or vice versa).
- **Reconcile/prune interaction**: `deploy_reconcile` lists orphans in the `skills`/`config`
  units only, so it does not scan `~/.claude/agents/` at all — neither the deployed role files
  nor a coexisting user agent are ever flagged or pruned by reconcile.
- **Non-Claude homes**: on assistant homes that do not consume role-agents
  (Cursor/Gemini/Codex/Antigravity), the feature must not deploy broken or ignored config.
- **Security-work routing**: a security-sensitive task must never be routed to the cheapest
  tier even when it looks mechanical.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The integration MUST provide a vendored, config-only set of named role-agents
  (no runtime code), each binding a role to a model tier and a reasoning-effort level. The
  set MUST be the six pilotfish roles: a read-only lookup role (scout), a search-override
  role (`Explore`) that overrides the built-in search agent and is bound to the cheapest tier,
  a fully-specified mechanical-execution role, a judgment-execution role, a fresh-context
  verification role, and a security-sensitive-execution role. The search-override file MUST be
  named `Explore` with the **capital E** matching Claude Code's built-in `Explore` agent exactly,
  so the override binds on case-sensitive filesystems.
- **FR-002**: Each role's model MUST be specified in its frontmatter via a model **alias** —
  Claude Code's built-in aliases (`haiku`/`sonnet`/`opus`) — never a raw model ID inline in
  policy prose. Because built-in aliases float to the current model version, a model-version
  change requires no Manifest edit, and re-tiering a role is a single one-line frontmatter
  edit. If a role must be pinned to a specific model version, that pin is a documented,
  single-point per-role frontmatter override (still an alias-or-ID in one place, not a
  separate custom-alias resolution layer).
- **FR-003**: The integration MUST provide a delegation policy stating when the orchestrator
  delegates to each role, that it starts at the cheapest capable tier and escalates after
  repeated failure, and that delegated results are gated behind an independent fresh-context
  verification step before the orchestrator proceeds. Verification MUST be selective: it MUST
  gate mutating work, judgment work, and security-sensitive work, and MAY skip pure read-only
  lookups (scout/Explore), so verification cost does not undermine the cost-reduction target
  (SC-001).
- **FR-004**: Security-sensitive work MUST be routed to a dedicated higher-assurance role
  and MUST NOT be delegated to the cheapest tier. This routing is a security control and
  MUST NOT be silently removed or weakened by later edits.
- **FR-005**: The integration MUST be gated behind a bootstrap service toggle (enable and
  disable) whose state is recorded in the services configuration, consistent with how
  existing optional integrations are toggled.
- **FR-006**: Enabling the toggle MUST deploy exactly the pilotfish configuration to the
  Claude home; disabling MUST remove exactly that configuration (a manifest-scoped prune of the
  known role files + marker) and leave all other content unchanged — including any
  **user-authored agent that coexists in `~/.claude/agents/`**: the disable path MUST NOT
  remove the whole agents directory, only the files it deployed, and MUST keep the directory if
  a foreign agent remains.
- **FR-007**: Model availability and fallback for the built-in aliases are handled by Claude
  Code; the delegation policy MUST document this so orchestration degrades gracefully rather
  than failing. A role pinned to a specific model version (the FR-002 override) MUST document
  its fallback (e.g. to the corresponding built-in alias).
- **FR-008**: Deployment MUST NOT overwrite a pre-existing, **non-Manifest-owned** agents
  directory (one lacking Manifest's ownership marker) **when one of the six pilotfish role-file
  names is already present there**. On such a name collision, deployment MUST abort the pilotfish
  deploy step with a clear error naming the colliding file and MUST leave the existing files
  untouched (touch nothing) — never silently clobber, back up, or partially deploy around them.
  A user agent with a *different* name is not a collision and MUST NOT block enabling (so a
  disable that left a coexisting user agent behind cannot deadlock the next enable). The
  role-file directory is excluded from the wholesale config copy and deployed only by the gated
  step, so a disabled or foreign home is never clobbered. A re-run over a **Manifest-owned**
  deployment (marker present) reconverges to the same tree — an **idempotent no-op in effect,
  not a collision and not a skip of the enable path** — so repeated `bootstrap.sh` runs on an
  enabled integration succeed (Principle V, Bootstrap Reproducibility).
- **FR-009**: After adding the delegation-policy pointer to the always-loaded orchestration
  guide, the **deployed** guide (committed source **plus** the injected pointer line) MUST remain
  within its enforced context-budget cap — verified by a test that measures source + pointer, so
  enabling the integration can never push the always-loaded guide over budget.
- **FR-010**: With the integration enabled, the repository MUST pass all existing gates:
  naming taxonomy, context/budget checks, deploy reconcile/prune, and derived-doc sync.
- **FR-011**: The integration MUST attribute the upstream pilotfish project per its MIT
  license and record the version it was vendored from, to support future drift review.
- **FR-012**: The integration MUST be documented — the role set, the delegation policy, the
  toggle, the role→alias mapping (and what each built-in alias currently resolves to), and how
  it relates to Manifest's existing model-selection practice.
- **FR-013**: The role-agents MUST be deployed to the Claude home only in this feature.
  Role-agents are a Claude Code construct that the other assistant homes (Cursor, Gemini,
  Codex, Antigravity) do not consume, so the feature MUST NOT deploy role-agent files to
  those homes. Extending the role/tier idea to other homes is explicitly out of scope for
  this feature and deferred to a possible follow-up.
  > **Update (2026-07-11, cursor-feature-parity WS-5)**: Cursor 2.x shipped native subagent
  > support (`~/.cursor/agents/*.md`) after this FR was written, closing the gap this FR
  > anticipated. Cursor is now a second provisioned pilotfish target — see
  > `docs/superpowers/specs/2026-07-11-cursor-feature-parity-design.md` §WS-5 and
  > `configs/claude/scripts/generate_cursor_agents.py`. Gemini/Codex/Antigravity still have no
  > subagent-file mechanism and remain out of scope; this FR's text is left as originally
  > written for the historical record.
- **FR-014**: The delegation policy MUST be deployed as its own read-on-demand file (a
  reference document), with only a one-line pointer added to the always-loaded
  `configs/claude/CLAUDE.md` Reference Index. The full policy MUST NOT be inlined into the
  always-loaded guide, so that always-loaded byte cost stays minimal and the guide remains
  within its context-budget cap (FR-009).
- **FR-015**: The pilotfish role-agents MUST be introduced as a distinct, self-contained
  layer that complements — and does not refactor — Manifest's existing multi-agent
  facilities (the subagent-driven-development workflow and the parallel-agent
  cross-verification script). The relationship MUST be documented (FR-012); unifying them
  into a single shared model-selection source is explicitly out of scope for this feature.
- **FR-016**: The integration MUST NOT change the deployed main-session model, its fallback
  chain, or `settings.json`/`settings.local.json`. It deploys the role-agents and the
  delegation-policy reference only; because roles use built-in model aliases, no model-alias
  definition file and no settings change is deployed. Manifest's existing main-session model
  and settings behavior MUST remain intact.

### Key Entities

- **Role Agent**: a named, config-only unit of delegatable work bound to one model alias and
  one reasoning-effort level (e.g. read-only lookup, mechanical execution, judgment
  execution, verification, security execution).
- **Model Alias**: the built-in Claude Code model alias a role's frontmatter names —
  `haiku` (cheapest), `sonnet` (mid), `opus` (high). Aliases float to the current model
  version (e.g. `opus`→Opus 4.8), so a role's model is changed by editing that one role's
  alias; the "frontier"/orchestrator model is the unchanged main session (FR-016), not a
  deployed alias.
- **Delegation Policy**: the orchestrator-facing rules for choosing a role, escalating on
  failure, and gating results behind fresh-context verification.
- **Service Toggle**: the enable/disable state for the integration, recorded in the services
  configuration and honored by deployment.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a representative multi-task workload, enabling cost-tiered orchestration
  reduces model cost by at least 40% relative to running every unit of work on the frontier
  tier, while verifier-confirmed task outcomes remain equivalent.
- **SC-002**: Re-tiering a role requires editing one line (its `model:` alias) in one file and
  zero lines of policy prose, and that role reflects the change after a single redeploy; a
  model-version change requires zero Manifest edits (built-in aliases float to the current
  version).
- **SC-003**: Enabling and then disabling the integration returns the Claude home to a state
  identical to never having enabled it, verifiable by a clean diff.
- **SC-004**: With the integration enabled, 100% of the repository's quality gates pass.
- **SC-005**: 100% of security-sensitive tasks are routed to the higher-assurance role; none
  are routed to the cheapest tier.
- **SC-006**: A contributor can enable the integration and confirm correct role deployment in
  under 5 minutes by following the documentation.

## Assumptions

- **Integration approach**: the role-agents and delegation policy are vendored-and-adapted
  into Manifest's deployed config (rather than depending on pilotfish's upstream installer),
  so Manifest owns deployment, gate compliance, and model-pin reconciliation. Upstream drift
  is managed by recording the vendored version (FR-011) and periodic review.
- **Toggle default**: the integration defaults to disabled (opt-in), consistent with the
  existing graphify and skillclaw optional integrations.
- **Role→alias mapping** (built-in Claude Code aliases): read-only/search roles (scout,
  Explore) → `haiku`, low effort; fully-specified mechanical work (mech-executor) → `sonnet`,
  low effort; judgment and verification work (executor, verifier) → `opus`, medium effort;
  security-sensitive work (security-executor) → `opus`, high effort. The orchestrator/frontier
  model is the unchanged main session (FR-016), not a deployed alias. Aliases float to current
  versions (`opus`→Opus 4.8, `sonnet`→Sonnet 5, `haiku`→Haiku 4.5); Claude Code handles model
  availability/fallback (FR-007).
- **No current collision**: the deployed agents directory is assumed to hold no
  Manifest-authored agent definitions today that would collide with the pilotfish role names;
  this is verified during planning (FR-008 covers the runtime case regardless).
- **Config-only**: the integration introduces no runtime service or daemon; it is Markdown
  agent definitions, policy text, and toggle wiring only — no `settings.json` change.
- **Reversibility unit**: "exactly the pilotfish configuration" (FR-006) means the six vendored
  agent files, the delegation-policy reference, and the one-line guide pointer — a bounded,
  enumerable set. No settings alias is added (FR-016).

## Out of Scope

- Deploying role-agents to non-Claude assistant homes (Cursor, Gemini, Codex, Antigravity);
  the role/tier idea may be formalized for them in a later feature (per FR-013). **Cursor**:
  done in the cursor-feature-parity WS-5 follow-up (2026-07-11, see the FR-013 update note
  above); Gemini/Codex/Antigravity remain out of scope (no subagent-file mechanism).
- Inlining the delegation policy into the always-loaded orchestration guide; it ships as a
  read-on-demand reference (per FR-014).
- Refactoring the existing subagent-driven-development skill or the parallel-agent
  cross-verification script to share a single model-selection source; pilotfish ships as a
  complementary layer (per FR-015).
- Any runtime service, daemon, or code component; the integration is config-only.
