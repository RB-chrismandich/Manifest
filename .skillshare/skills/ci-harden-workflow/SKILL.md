---
name: ci-harden-workflow
description: Build or harden a CI workflow that runs privileged actions (deploys, bot/agent invocation, secret use) on comment/PR triggers — identity gates, CODEOWNERS, branch protection, environments. Counterpart to ci-audit-triggers (which audits; this builds/governs).
---
# Secure a Privileged Comment-/Event-Triggered Workflow

A workflow that invokes an agent or uses a secret in response to `issue_comment` / `pull_request_target` /
`workflow_run` runs with the *base* repo's token and secrets — even for fork PRs. Left ungated this is the "pwn request"
hole. Goal: lock down *who can change or trigger the control* without losing the auto-run-on-PRs value. To *audit an
existing* workflow for these holes (expression injection, fork head-ref checkout), use `ci-audit-triggers`; this skill
is the build/governance side.

1. **Name the privilege.** State exactly which secret or write permission the job can reach. That is the blast radius
   you are gating.
2. **Gate on server-set identity, not just string matching.** Require ALL of: the mention/command text is present; the
   actor is genuinely trusted; and `github.event.comment.user.type != 'Bot'` (stops self-trigger loops). Put the gate at
   **job level** (`if:`) so no step runs in an untrusted context. `author_association ∈ {OWNER, MEMBER, COLLABORATOR}`
   is server-set and not spoofable, but it is **not a write-access check** — `COLLABORATOR` includes read-/triage-only
   collaborators and `MEMBER` is any org member, so it can admit principals who cannot actually change the repo. For a
   privileged trigger, confirm the real permission level (e.g. `gh api
   repos/{owner}/{repo}/collaborators/{user}/permission` → `admin`/`write`) rather than `author_association` alone.
3. **Treat default-branch execution as a feature.** `issue_comment`, `workflow_run`, and — since GitHub's change
   effective 2025-12-08 — `pull_request_target` all run the copy of the YAML on the **default branch** (the workflow
   file, checkout commit, and `GITHUB_REF`/`GITHUB_SHA` for `pull_request_target` now come from the default branch
   regardless of the PR's base branch) — never the PR's own copy. So a PR that weakens the gate is inert until merged;
   the real attack surface is "who can change the workflow on the default branch," and testing the gate must happen
   post-merge. (Inertness covers the trigger's YAML only — a script or allowlist *file* the job checks out at runtime
   from the PR head ref is a separate vector.)
4. **Set least-privilege `permissions:`.** Grant only what's needed (e.g. `contents: read`, `pull-requests: read`, plus
   `pull-requests: write` or `issues: write` only if posting a reaction/failure comment). Always set `permissions:`
   explicitly rather than inheriting the default token scope (which varies by repo/org setting).
5. **Protect the control file.** Add `CODEOWNERS` covering `/.github/workflows/` and any allowlist/config the gate
   reads; enable branch protection on the default branch: require PR + ≥1 review + "require review from Code Owners" +
   dismiss-stale-reviews + block force-push/deletion. This is what actually enforces "no one edits the controls."
6. **Keep a sole maintainer un-lockable.** Under classic branch protection set `enforce_admins: false` so the owner can
   still admin-merge their own PRs while collaborators remain fully gated (with rulesets, express the same via a bypass
   actor). Expect "review required" on your own PRs as a result.
7. **For a hard human gate on every run,** put the secret in a GitHub Environment with required reviewers and add
   `environment:` to the job — it pauses for an approval click before reading the secret. Trade-off: forfeits full
   automation; use only when a human-in-the-loop per run is wanted.
8. **SHA-pin every action** (`uses: org/action@<sha> # vN`) and verify the action's real repo + input names before
   pinning, so a moved tag can't change behavior under you. Also confirm the action doesn't inline-template any input
   you feed it from untrusted data — a composite that does `--arg x "${{ inputs.x }}"` re-creates the injection your
   `with:` hand-off was meant to avoid (sanitize the value first, e.g. a branch name against `^[A-Za-z0-9._/-]+$`). And
   check the action's own transitive `uses:` are pinned, not moving tags.
9. **Validate statically and reason the gate through.** Run `actionlint`; confirm a fork/non-collaborator comment cannot
   run before relying on the live trigger.
