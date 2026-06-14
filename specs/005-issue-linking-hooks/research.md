# Phase 0 Research: Issue-Linking Git Hooks

Resolves the open mechanism questions left by the spec (Clarifications) and Technical Context. Each item: **Decision · Rationale · Alternatives considered**.

## R1 — Trigger mechanism (how a hook fires on "PR opened" and "branch commit")

**Decision**: Use the repo's existing **`ai-hooks-integration` unified `PostToolUse` hook** as the primary trigger, matched on the Bash command text:
- PR skill fires when the matched command creates a PR/MR — patterns `git_ops.sh pr-create`, `gh pr create`, `glab mr create`.
- Commit skill fires when the matched command commits — patterns `git commit`, `git_ops.sh`-mediated commits.

Ship a secondary, **opt-in guarded native `post-commit` git hook** (installed by `install_issue_hooks.sh`) for developers who commit outside an AI tool (raw CLI). The native hook only calls `issue_support.sh sync-commit HEAD`.

**Rationale**: There is **no native git event for "PR created"** — PR/MR creation is a platform (`gh`/`glab`) action, not a git operation — so a git hook alone cannot cover the primary P1 trigger. The unified `PostToolUse` mechanism already exists in this repo, is cross-tool (Claude Code / Gemini / Cursor), and observes the actual command that creates the PR, making it the only mechanism that covers *both* triggers uniformly. Idempotency makes double-firing (e.g., unified hook *and* native hook both catching a commit) harmless.

**Coverage boundary (explicit)**: PostToolUse observes the *command*, so PR creation flows through an AI-tool-mediated command or `git_ops.sh pr-create` are covered. **Not** auto-covered in v1: PR creation via the platform **web UI**, or raw `gh pr create`/`glab mr create` typed directly in a terminal outside a tool — no native git "PR-opened" event exists to hook. Documented in spec Assumptions/Edge Cases; the manual `issue_support.sh sync-pr <N>` invocation and a future server-side `pull_request: opened` CI trigger are the complements. The commit hook keeps the issue current on the next commit regardless.

**Alternatives considered**:
- *Native git hooks only* — rejected: cannot observe PR creation; also per-clone `.git/hooks` install is invisible to the config-as-code source of truth.
- *Server-side CI webhook for PR-opened as the v1 primary* — deferred: closes the web-UI gap but adds per-repo CI config and can't run the interactive create-issue prompt; noted as the future universal-coverage complement.
- *Wrapper subcommand* (`git_ops.sh pr-create` calls the engine inline) — rejected as the *primary* mechanism because it misses direct `gh pr create`; kept implicitly, since matching `git_ops.sh pr-create` in the PostToolUse pattern covers the wrapper path too.
- *Platform webhooks (GitHub Actions / GitLab CI on PR-opened)* — rejected for v1: server-side, can't run the interactive create-issue prompt, and adds per-repo CI config (violates "no per-repo config" goal). Noted as a future server-side complement.

## R2 — Idempotency & de-duplication without local state

**Decision**: Derive "already synced" entirely from **live tracker state**, two signals:
1. **Status label** — a forward-only transition is a no-op if the issue is already at/after the target label (`planned`→`in-progress`→`needs-review`→`done`).
2. **Marker comment** — the engine's back-link comment embeds a hidden marker line `<!-- issue-support:sync v1 pr=<n>|commit=<branch> -->`. Before commenting, the engine lists issue comments and skips if a matching marker already exists; otherwise it edits/reuses that comment (via `git_ops.sh issue-comment-edit-last` where applicable).

**Rationale**: No local file means nothing to drift, nothing to clean up, and a fresh clone or a different machine behaves identically (Constitution V). The label check makes rapid successive commits sub-second no-ops (SC-003/SC-007). The marker check prevents comment spam even across machines.

**Alternatives considered**:
- *Local marker file* (`.git/issue-support-state`) — rejected: per-clone drift, not visible to other contributors, violates the stateless goal.
- *Rely on label only* — rejected: labels can't dedup the back-link comment, and a manually-moved label would suppress the comment.

## R3 — Resolving the linked issue (association precedence)

**Decision**: Resolve in this fixed order, first match wins, collecting all distinct references when multiple are valid (FR-011):
1. **Branch-number prefix** — leading `NNN-` on the branch name maps to issue `#NNN` (the repo's existing convention, e.g. `005-issue-linking-hooks`). Validate the number actually exists as an open issue via `git_ops.sh issue-view` before acting.
2. **PR/MR body references** — `Closes/Fixes/Resolves #N` and bare `#N` in the description (from `git_ops.sh pr-view`).
3. **Commit trailers/refs** — `#N`, `Closes #N`, or a `Refs:`/`Issue:` trailer in commit messages on the branch.

If step 1's number does not resolve to a real issue, fall through to 2/3 rather than acting on a non-existent issue. Conflicting/ambiguous multi-issue results are reported, not silently picked (FR-012).

**Rationale**: Branch prefix is the highest-signal, lowest-cost source and is already the project standard; explicit body/commit references catch ad-hoc and multi-issue cases. Validating existence avoids the "branch numbered 005 but issue #5 is unrelated" trap.

**Alternatives considered**:
- *Body references first* — rejected: most branches here are numbered, so prefix-first minimizes API calls.
- *Fuzzy title matching as a resolver* — rejected for resolution (too lossy); reused only for the create-issue dedup check (R4).

## R4 — Best-of-breed issue creation (when none is linked)

**Decision**: The create path:
1. **Dedup first** — search open issues (`git_ops.sh issue-list`) for a title/branch-context match; if found, link to it instead of creating (FR-009a).
2. **Prompt for confirmation** — interactive only; non-interactive context defaults to "do not create" + warn (FR-009).
3. **Create from template** — the **engine-owned** template `configs/claude/scripts/templates/issue_support_issue.md` (resolved relative to the engine, not the calling skill, so both `pr-issue-sync` and `commit-issue-sync` get identical output): context summary, acceptance-criteria stub, and bidirectional links to branch/PR/commit; apply the canonical `planned` label; then immediately run the normal sync so the new issue enters the same lifecycle (FR-009b/c).

**Rationale**: Matches the user's "best-of-breed" directive — an auto-created issue is indistinguishable from a hand-authored one and never becomes tracker debt. Dedup-before-create prevents the most common failure mode (a second issue for work that already has one).

**Alternatives considered**:
- *Auto-create without prompt* — rejected (spec decision): noise risk.
- *Bare-title stub* — rejected: low-value tracker debt, the exact thing "best-of-breed" rules out.

## R5 — Platform scope (GitHub / GitLab / Linear)

**Decision**: v1 supports **GitHub and GitLab** via `git_ops.sh` + `git_platform.sh`, per the explicit feature request. **Linear is a designed extension point, not v1 scope**: the engine routes all tracker actions through a thin internal `tracker_*` indirection so a future `linear_ops.sh` backend can be added without touching the skills or hook wiring.

**Rationale**: The request named github/gitlab; `linear_ops.sh` exists but Linear has no git-branch/PR coupling (it's issue-only), so its trigger story differs and belongs in a follow-up. Keeping the indirection avoids a future rewrite.

**Alternatives considered**:
- *Include Linear in v1* — rejected: scope creep beyond the request and a different trigger model; deferred with a clean seam.

## R6 — Timeout / fail-open enforcement

**Decision**: The engine wraps its tracker work in a soft timeout using the platform `timeout` helper already present in `bootstrap/lib/platform.sh` (or `timeout`/`gtimeout`), bounded by `hook_timeout_seconds` (config, default 5). On timeout, non-zero from any `git_ops.sh` call, missing CLI, or missing token scope, it prints a single `err()` warning and exits **0** so the git action proceeds (FR-008, SC-002). `commit_hook_mode` is `sync`-only in **v1**; `background` is a reserved value — if configured now, the engine falls back to `sync` and warns (no silent/undefined behavior), preserving the option to add true background dispatch later without a config redesign.

**Rationale**: Reuses existing timeout helpers; exit-0-on-failure is the concrete mechanism that guarantees zero blocking failures. Idempotency (R2) makes the dropped run recoverable on the next trigger.

**Alternatives considered**:
- *Hard timeout that aborts the git action* — rejected: violates fail-open.
- *No timeout* — rejected: a hung tracker would stall every commit (the Decision-1 disqualifier).

## Resolved unknowns

All Technical Context items are now concrete; **no NEEDS CLARIFICATION remain**. Config keys introduced in `command_config.yml`:
- `tool_policies.pr-issue-sync`: `enabled` (default `false`), `hook_timeout_seconds` (default 5)
- `tool_policies.commit-issue-sync`: `enabled` (default `false`), `hook_timeout_seconds` (default 5), `commit_hook_mode` (`sync`|`background`, default `sync` — commit-only; not applicable to the PR hook; `background` reserved for v2, falls back to `sync`+warn in v1)

`enabled` is a **runtime gate**: the engine reads it and exits as a no-op when false, so disabling is a one-line config change without uninstalling the hook (FR-015). The installer sets it `true` on `--enable`.
