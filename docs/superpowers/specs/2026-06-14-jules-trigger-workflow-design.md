# Design: Jules Bot Trigger Workflow

**Date**: 2026-06-14
**Status**: Approved (design) — pending implementation plan
**Author**: Brainstormed via `/superpowers:brainstorming`

## Problem

Google Jules is a remote coding agent integrated with this repo (it opens PRs
via personas — Forge, Bolt, Palette, Sentinel). But it is **not a GitHub-native
reviewer**: requesting it as a PR reviewer or assignee is silently ignored, and a
plain `@google-labs-jules` mention does nothing because no automation acts on it.
The only reliable trigger today is launching a session from jules.google by hand.

We want a mention on a PR (or issue) — e.g. "@google-labs-jules please review
this PR" — to **actually invoke Jules**, scoped safely to trusted users.

## Goal

A GitHub Actions workflow that, when a **trusted** user posts a comment
mentioning `@google-labs-jules`, invokes the Google Jules action against the
right branch and gives visible feedback.

## Decisions (from brainstorming)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Trigger gate** | `author_association ∈ {OWNER, MEMBER, COLLABORATOR}` | GitHub-set, not spoofable, zero hardcoded usernames, auto-correct as the team changes. Fork/outside authors are `CONTRIBUTOR`/`NONE` → blocked. |
| **Start branch** | PR-aware: PR head if the comment is on a PR, else `main` | Lets Jules iterate on the branch of the PR you mentioned it from. |
| **Feedback** | 👀 reaction on receipt + comment on failure | Lightweight "received" signal; failures surface without digging the Actions tab. |
| **Structure** | Single workflow, single job, sequential steps | Smallest thing that satisfies the above; matches the repo's single-file `ci.yml` style. |

## Architecture

One file: `.github/workflows/jules-trigger.yml`. One job, `invoke`.

```
issue_comment:[created]
        │
        ▼
   job if: gate ──(fails)──▶ no run
   (mention AND trusted AND not-a-bot)
        │ (passes)
        ▼
   ① 👀 react to the comment
        ▼
   ② resolve start branch (PR head ‖ main)
        ▼
   ③ invoke Jules (pinned action)
        ▼
   ④ if failure() → comment linking the run
```

`issue_comment` fires for **both** issues and PRs (PRs are issues in GitHub's
model); `types: [created]` means edits do not retrigger.

## Security model

The job-level `if:` is the security boundary. It requires **all** of:

1. `contains(github.event.comment.body, '@google-labs-jules')` — a deliberate mention.
2. `author_association` is `OWNER`, `MEMBER`, or `COLLABORATOR` — write-access trust.
3. `github.event.comment.user.type != 'Bot'` — prevents a bot's own comment
   (e.g. one that quotes the mention) from self-triggering a loop.

**Why this matters:** `issue_comment` workflows run in the **base repo's**
context with its secrets, even for comments on fork PRs. The `author_association`
gate is what stops an outside contributor from ever reaching the `JULES_API_KEY`
step. Without it, anyone who can comment could task an autonomous agent that has
repository write access.

**Least-privilege permissions:**

```yaml
permissions:
  contents: read          # default
  pull-requests: read     # resolve the PR head ref
  issues: write           # 👀 reaction + failure comment (PR comments are issues)
```

## Components (steps)

1. **Acknowledge** — `actions/github-script` (SHA-pinned):
   `reactions.createForIssueComment(..., content: 'eyes')`.
2. **Resolve start branch** — `actions/github-script` (SHA-pinned), `id: branch`:
   if `context.payload.issue.pull_request` is set → `pulls.get(...).data.head.ref`;
   else `main`. Exposed as `steps.branch.outputs.ref`.
3. **Invoke Jules** — the Google Jules action (**exact path verified + SHA-pinned
   at implementation time**; examples reference `google-labs-code/jules-invoke@v1`
   while the source repo may be `…/jules-action`):
   - `prompt: ${{ github.event.comment.body }}` (raw comment; mention-stripping is
     deliberately out of scope)
   - `jules_api_key: ${{ secrets.JULES_API_KEY }}`
   - `starting_branch: ${{ steps.branch.outputs.ref }}`
4. **Report failure** — `if: failure()`, `actions/github-script` (SHA-pinned):
   `issues.createComment` linking `…/actions/runs/<runId>`.

## Repo conventions to honor

- **SHA-pin every action** with a `# vN` trailing comment (repo rule; see
  `ci.yml`). Floating `@v1` tags are not used here.
- **Explicit `permissions:`** block (every existing workflow has one).
- **`concurrency`**: `group: jules-${{ github.event.issue.number }}`,
  `cancel-in-progress: false` — never cancel an in-flight Jules invocation when a
  second comment arrives.

## Prerequisites (owner action, outside this workflow)

- Add the **`JULES_API_KEY`** repository secret (Settings → Secrets and variables
  → Actions). The workflow cannot run end-to-end without it; until then step ③
  fails and step ④ posts the failure comment.

## Error handling & edge cases

- **Missing secret / action error** → step ③ fails → step ④ posts a failure
  comment linking the run (Q3 behavior). Reaction from step ① already landed.
- **Comment on a plain issue** (not a PR) → `starting_branch = main`.
- **Untrusted / fork / bot commenter** → job `if:` is false → no run, no secret
  exposure.
- **Edited comment** → no retrigger (`types: [created]`).
- **Mention inside a code block / quote by a trusted user** → would still trigger;
  accepted risk, since the commenter is already trusted.

## Testing strategy

- **Static**: validate workflow YAML (`yamllint`, and `actionlint` if available)
  — syntax, the `if:` expression, and pinned `uses:` refs.
- **Gate reasoning**: a comment from a non-collaborator or a bot does not satisfy
  the `if:`; documented as the security assertion (cannot be unit-tested without a
  second account).
- **Live**: the owner adds `JULES_API_KEY`, comments `@google-labs-jules …` on a
  PR, and confirms 👀 + a Jules session on the PR's branch. Failure path confirmed
  by triggering before the secret exists (expect the failure comment).

## Out of scope (YAGNI)

- Stripping the `@google-labs-jules` mention from the prompt.
- Multi-job split (gate-and-resolve → invoke) or a reusable composite action.
- Adding `actionlint` to the CI pipeline.
- Explicit username allowlist (superseded by `author_association`).
