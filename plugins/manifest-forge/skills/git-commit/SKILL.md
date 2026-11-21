---
name: git-commit
description: "Run an authorized, scoped commit-and-publication workflow with safe failure handling. Use for full commit-and-push requests, not a bare local commit."
---

# Scoped Commit and Publication

Complete only the delivery stages authorized by the user. A request to commit does
not by itself authorize a push, PR/MR, merge, deployment, or release. Never expand
authorization. Do not require routine commit-message confirmation once commit
delivery is authorized; protected-branch and repository authorization controls
still apply.

## 1. Preflight and scope

1. Read the repository's committed instructions, supported checks, and CI contract
   relevant to the changed files. Run `/manifest-code-quality:project-verify`
   when verification is requested or required by the repo. Do not generate or
   refresh documentation unless the user requested documentation work; run a
   docs workflow only when requested.
2. Establish repository identity (`git rev-parse --show-toplevel` and the
   configured remote URL), source branch, intended target branch, and intended
   remote. Detect GitHub/GitLab from the selected remote using the repository's
   provider helper when available; use only that provider's CLI (`gh` or `glab`).
   Never assume `origin`, `main`, or GitHub.
3. Confirm local Git author identity with `git config --local user.name` and
   `git config --local user.email`. If either is absent or wrong, stop and report
   the needed repository-local setting; never change global identity.
4. Identify the exact task-owned paths and hunks. Inspect both the index and work
   tree (`git status --short`, `git diff --cached`, `git diff`). Stage only the
   authorized paths/hunks. Preserve all unrelated staged and unstaged changes.
   Use path-limited staging or interactive hunk staging; never use `git add -A`
   or stage the whole tree. If unrelated index entries or mixed hunks cannot be
   excluded safely without altering user state, stop with the exact paths and
   blocker. Never reset, stash, or unstage user changes.
5. The task-owned staged diff must be non-empty and match the requested change.
   An empty or unintended diff is a blocker, not success.

## 2. Commit

Use the supplied commit message or derive a concise one from the task-owned diff.
Do not ask for routine message approval in an already authorized delivery.
Inspect issue references and add closing keywords only when their effect is
intended and the issue is verified open with the selected provider.

Run the repository-supported checks before committing. Every multi-command shell
sequence must fail fast (`&&` between dependent commands or a guarded
`set -euo pipefail` script); do not rely on a later command masking a failure.
Commit only the task-owned paths/hunks. If safe index isolation is uncertain,
stop rather than risk including or discarding unrelated changes.

After commit, verify the new commit SHA, author, subject, and exact commit diff
against the intended task-owned changes. A failed commit ends the workflow:
do not push, look up, or create a PR/MR.

## 3. Push and open the existing or new PR/MR

Proceed only when separately authorized. Pin the verified commit SHA, intended
remote, source branch, and target branch. Use fail-fast commands and verify each
transition before proceeding:

1. Push the source branch to the intended remote.
2. Read the remote source-branch SHA and require it to equal the verified commit
   SHA. A push command's exit status alone is not proof.
3. Inspect the source-to-target diff using the provider and repository's supported
   route. Require a non-empty diff whose changed paths/content are the intended
   task only. Empty, stale, or unintended differences are non-success; stop.
4. Look up an existing PR/MR for the exact source → target pair. Verify both
   branches and repository/project identity. Reuse and report the existing item;
   create one only when lookup establishes none exists.
5. GitHub uses `gh pr view` / `gh pr create`; GitLab uses `glab mr view` /
   `glab mr create`. Do not run GitHub-only commands for GitLab. Use explicit
   source and target arguments supported by the selected CLI.

If push succeeds but PR/MR lookup or creation fails, record that as partial
success: include the verified remote SHA and the exact safe continuation (look
up the existing source → target PR/MR, then create only if absent). Do not claim
publication succeeded. Never retry a create blindly after an ambiguous result.

## 4. Conflict and failure handling

Resolve conflicts from actual task intent and project contracts. Do not use a
blanket preference for local functional changes or remote documentation. Preserve
both sides only when their semantics are compatible. If intent is ambiguous or
the conflict changes behavior whose contract is not clear, stop and identify the
conflicted paths and decision needed; do not choose a side automatically.

Do not retry a failed command blindly. Diagnose the observed failure and retry
only when a specific safe correction is known. Never treat a skipped check,
empty diff, failed commit, stale remote SHA, or failed PR/MR operation as success.

## 5. Report

Report the repository, source/target branches, task-owned paths, checks and their
actual outcomes, commit SHA, push/PR/MR status, evidence, verification limits,
and unresolved blocker. Distinguish completed stages from stages not requested
or not authorized. Never claim a push, PR/MR, merge, or deployment without
read-back evidence.
