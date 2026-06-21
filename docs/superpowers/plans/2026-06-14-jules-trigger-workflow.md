# Jules Trigger Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub Actions workflow that invokes Google Jules when a trusted user mentions `@google-labs-jules` in an issue/PR comment.

**Architecture:** One workflow file, one job. A job-level `if:` gate (mention + `author_association` OWNER/MEMBER/COLLABORATOR + not-a-bot) is the security boundary. Steps run sequentially: react 👀 → resolve start branch (PR head, else `main`) → invoke the SHA-pinned Jules action → comment on failure.

**Tech Stack:** GitHub Actions; `actions/github-script` (v9.0.0) for the GitHub API calls; `google-labs-code/jules-action` (v1.0.0) for the invocation. Static validation via `actionlint`.

**Design doc:** `docs/superpowers/specs/2026-06-14-jules-trigger-workflow-design.md`
**Branch:** `feat/jules-trigger-workflow`

---

## File Structure

- **Create:** `.github/workflows/jules-trigger.yml` — the entire feature. One job, four steps, gated by `author_association`.

There is no application code to test in isolation: a GitHub workflow is verified by **static analysis** (`actionlint`, which checks YAML, `if:` expression syntax, and `uses:` refs) plus a **live trigger** the owner runs once. Each task below adds one valid, committable slice and validates it with `actionlint`.

## Pinned references (already resolved — use verbatim)

| Action | Pinned ref |
|--------|-----------|
| `actions/github-script` | `actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0` |
| `google-labs-code/jules-action` | `google-labs-code/jules-action@bff7875eaa123cac6742b7cfc51005b95ba4d566  # v1.0.0` |

Jules action inputs (from its `action.yml`): `prompt` (required), `jules_api_key` (required), `starting_branch` (optional, default `main`).

## Prerequisite: install actionlint (one-time)

- [ ] **Step 0: Install actionlint**

Run: `brew install actionlint`
Expected: actionlint installed (or "already installed"). Verify: `actionlint --version` prints a version.

---

## Task 1: Scaffold the workflow — triggers, permissions, gate, and the 👀 step

**Files:**
- Create: `.github/workflows/jules-trigger.yml`

- [ ] **Step 1: Write the complete scaffold file**

Create `.github/workflows/jules-trigger.yml` with exactly this content (a valid workflow that gates and reacts, nothing else yet):

```yaml
name: Jules Trigger

on:
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: read
  issues: write

concurrency:
  group: jules-${{ github.event.issue.number }}
  cancel-in-progress: false

jobs:
  invoke:
    # Security boundary (design §Security model): only a deliberate mention from
    # a trusted, non-bot commenter ever reaches the JULES_API_KEY step. issue_comment
    # runs with the base repo's secrets even for fork PRs, so author_association is
    # what blocks outside contributors (CONTRIBUTOR/NONE).
    if: >-
      contains(github.event.comment.body, '@google-labs-jules') &&
      (github.event.comment.author_association == 'OWNER' ||
       github.event.comment.author_association == 'MEMBER' ||
       github.event.comment.author_association == 'COLLABORATOR') &&
      github.event.comment.user.type != 'Bot'
    runs-on: ubuntu-latest
    steps:
      - name: Acknowledge with reaction
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            await github.rest.reactions.createForIssueComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              comment_id: context.payload.comment.id,
              content: 'eyes',
            });
```

- [ ] **Step 2: Validate with actionlint**

Run: `actionlint .github/workflows/jules-trigger.yml`
Expected: no output, exit code 0 (no errors). If actionlint reports expression or `uses:` errors, fix them before continuing.

- [ ] **Step 3: Confirm the gate has all three conditions**

Run: `grep -E "author_association|user.type|google-labs-jules" .github/workflows/jules-trigger.yml`
Expected: lines showing the mention check, the three `author_association` comparisons, and the `user.type != 'Bot'` check.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/jules-trigger.yml
git commit -m "feat(jules-trigger): scaffold gated workflow with reaction step"
```

---

## Task 2: Resolve the start branch (PR head, else main)

**Files:**
- Modify: `.github/workflows/jules-trigger.yml` (add a step after "Acknowledge with reaction")

- [ ] **Step 1: Add the resolve-branch step**

Insert this step immediately **after** the `Acknowledge with reaction` step (same `steps:` list, same indentation):

```yaml
      - name: Resolve start branch
        id: branch
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            let ref = 'main';
            if (context.payload.issue.pull_request) {
              const pr = await github.rest.pulls.get({
                owner: context.repo.owner,
                repo: context.repo.repo,
                pull_number: context.payload.issue.number,
              });
              ref = pr.data.head.ref;
            }
            core.setOutput('ref', ref);
```

- [ ] **Step 2: Validate with actionlint**

Run: `actionlint .github/workflows/jules-trigger.yml`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/jules-trigger.yml
git commit -m "feat(jules-trigger): resolve PR head branch (else main)"
```

---

## Task 3: Invoke Jules

**Files:**
- Modify: `.github/workflows/jules-trigger.yml` (add a step after "Resolve start branch")

- [ ] **Step 1: Add the invoke step**

Insert this step immediately **after** the `Resolve start branch` step:

```yaml
      - name: Invoke Jules
        uses: google-labs-code/jules-action@bff7875eaa123cac6742b7cfc51005b95ba4d566  # v1.0.0
        with:
          prompt: ${{ github.event.comment.body }}
          jules_api_key: ${{ secrets.JULES_API_KEY }}
          starting_branch: ${{ steps.branch.outputs.ref }}
```

- [ ] **Step 2: Validate with actionlint**

Run: `actionlint .github/workflows/jules-trigger.yml`
Expected: no output, exit code 0. (actionlint will not flag the missing secret — that is a runtime/repo-settings concern, covered in Task 5.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/jules-trigger.yml
git commit -m "feat(jules-trigger): invoke Jules with resolved branch"
```

---

## Task 4: Comment on failure

**Files:**
- Modify: `.github/workflows/jules-trigger.yml` (add a step after "Invoke Jules")

- [ ] **Step 1: Add the failure-report step**

Insert this step immediately **after** the `Invoke Jules` step (it runs only if a prior step failed):

```yaml
      - name: Report failure
        if: failure()
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.issue.number,
              body: `⚠️ Jules invocation failed — see the [workflow run](${runUrl}).`,
            });
```

- [ ] **Step 2: Validate with actionlint**

Run: `actionlint .github/workflows/jules-trigger.yml`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/jules-trigger.yml
git commit -m "feat(jules-trigger): post a comment when invocation fails"
```

---

## Task 5: Final verification + owner prerequisites

**Files:**
- Reference only: `.github/workflows/jules-trigger.yml` (no further edits expected)

The complete file should now read exactly:

```yaml
name: Jules Trigger

on:
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: read
  issues: write

concurrency:
  group: jules-${{ github.event.issue.number }}
  cancel-in-progress: false

jobs:
  invoke:
    if: >-
      contains(github.event.comment.body, '@google-labs-jules') &&
      (github.event.comment.author_association == 'OWNER' ||
       github.event.comment.author_association == 'MEMBER' ||
       github.event.comment.author_association == 'COLLABORATOR') &&
      github.event.comment.user.type != 'Bot'
    runs-on: ubuntu-latest
    steps:
      - name: Acknowledge with reaction
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            await github.rest.reactions.createForIssueComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              comment_id: context.payload.comment.id,
              content: 'eyes',
            });

      - name: Resolve start branch
        id: branch
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            let ref = 'main';
            if (context.payload.issue.pull_request) {
              const pr = await github.rest.pulls.get({
                owner: context.repo.owner,
                repo: context.repo.repo,
                pull_number: context.payload.issue.number,
              });
              ref = pr.data.head.ref;
            }
            core.setOutput('ref', ref);

      - name: Invoke Jules
        uses: google-labs-code/jules-action@bff7875eaa123cac6742b7cfc51005b95ba4d566  # v1.0.0
        with:
          prompt: ${{ github.event.comment.body }}
          jules_api_key: ${{ secrets.JULES_API_KEY }}
          starting_branch: ${{ steps.branch.outputs.ref }}

      - name: Report failure
        if: failure()
        uses: actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9.0.0
        with:
          script: |
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.issue.number,
              body: `⚠️ Jules invocation failed — see the [workflow run](${runUrl}).`,
            });
```

- [ ] **Step 1: Final actionlint pass**

Run: `actionlint .github/workflows/jules-trigger.yml`
Expected: no output, exit code 0.

- [ ] **Step 2: Confirm all `uses:` are SHA-pinned (repo convention)**

Run: `grep -E "uses:" .github/workflows/jules-trigger.yml`
Expected: every `uses:` ends in a 40-char SHA with a `# vN` comment — no floating `@v1`/`@main` tags.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/jules-trigger-workflow
```

Expected: branch pushed. GitHub validates workflow syntax on push; check the repo's Actions tab shows no "invalid workflow file" error for `jules-trigger.yml`.

- [ ] **Step 4: Owner prerequisite — add the `JULES_API_KEY` secret**

This is a manual repo-settings action (cannot be scripted in the workflow):
1. Get a Jules API key from https://jules.google (account settings / API).
2. Repo → Settings → Secrets and variables → Actions → New repository secret.
3. Name: `JULES_API_KEY`, value: the key. Save.

Until this secret exists, the `Invoke Jules` step fails and the `Report failure` step posts the failure comment — which is the designed behavior.

- [ ] **Step 5: Live trigger test (owner)**

After the workflow is on the default branch (merge the PR, since `issue_comment` workflows run from the **default branch's** copy, not the PR branch):
1. On any open PR, comment: `@google-labs-jules please review this PR`.
2. Expect: a 👀 reaction appears on your comment within ~1 min, and a Jules session starts against that PR's head branch.
3. Negative check: confirm a comment **without** the mention, or from a non-collaborator, does **not** start a run (Actions tab shows no triggered run).

> **Important runtime note:** GitHub runs `issue_comment` workflows from the workflow file on the **repository default branch**, not from the PR's branch. So this workflow only takes effect once it is merged to `main`. Testing the trigger before merge will not run the new workflow.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Gate (mention + association + not-bot) → Task 1 `if:`. ✓
- PR-aware start branch → Task 2. ✓
- Invoke Jules (pinned, correct inputs) → Task 3. ✓
- 👀 reaction → Task 1; failure comment → Task 4. ✓
- Least-privilege permissions, concurrency, SHA-pinning → Task 1 scaffold + Task 5 Step 2. ✓
- `JULES_API_KEY` prerequisite → Task 5 Step 4. ✓
- Testing strategy (actionlint static + live trigger) → every task's validate step + Task 5 Step 5. ✓
- Default-branch runtime caveat → Task 5 note (catches the "tested on PR branch, nothing happened" trap). ✓

**Placeholder scan:** No TBD/TODO; all SHAs and inputs are concrete and verified. ✓

**Type/name consistency:** Step output `steps.branch.outputs.ref` (set via `core.setOutput('ref', …)` in Task 2) is consumed as `${{ steps.branch.outputs.ref }}` in Task 3. Action SHAs identical across all tasks. ✓
