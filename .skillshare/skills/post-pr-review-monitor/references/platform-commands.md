# Platform command cookbook

GitHub (`gh`) and GitLab (`glab`) commands for each phase, plus how to detect
the AI review bots. Read this when you need the exact invocation.

## Contents

- [Resolve PR + platform](#resolve-pr--platform)
- [CI / pipeline status](#ci--pipeline-status)
- [Detect Copilot](#detect-copilot)
- [Detect / tag Jules](#detect--tag-jules)
- [Fetch review feedback](#fetch-review-feedback)

## Resolve PR + platform

```bash
# Platform detection (repo helper): prints github | gitlab | git
configs/claude/scripts/git_platform.sh

# GitHub — PR for the current branch
gh pr view --json number,headRefName,baseRefName,url,state,isDraft,reviewRequests

# GitHub — explicit PR
gh pr view <N> --json number,headRefName,url,state,isDraft,reviewRequests,reviews

# GitLab — MR for the current branch / explicit
glab mr view
glab mr view <N>
```

If `gh pr view` errors with "no pull requests found", there is no PR for the
branch yet — ask before creating one.

## CI / pipeline status

```bash
# GitHub — block until all checks finish; exits non-zero if any failed
gh pr checks <N> --watch --interval 30

# GitHub — one-shot snapshot (table of check -> state)
gh pr checks <N>

# GitHub — logs for a failed run (find run-id from the checks output / Actions tab)
gh run view <run-id> --log-failed
gh run list --branch <branch> --limit 5   # locate the run-id

# GitLab — live pipeline status / MR pipeline
glab ci status --live
glab mr view <N>                # shows pipeline state
glab ci trace <job-id>          # job log
```

## Detect Copilot

GitHub Copilot code review posts as a bot. Identify it by login, not display name.

```bash
# Is Copilot a requested reviewer?
gh pr view <N> --json reviewRequests \
  --jq '.reviewRequests[] | select(.login // .name | test("[Cc]opilot"))'

# Has Copilot submitted a review? (bot login: copilot-pull-request-reviewer[bot])
gh api repos/{owner}/{repo}/pulls/<N>/reviews \
  --jq '.[] | select(.user.login | test("copilot")) | {state, id, body}'
```

- Login to match: `copilot-pull-request-reviewer[bot]` (case-insensitive
  `copilot` substring is a safe filter).
- If neither query returns anything, Copilot review is not on this PR — skip the
  Copilot phase. Do not try to add it; whether it runs is a repo/org setting.

GitLab: GitHub Copilot PR review is GitHub-specific; on GitLab this phase is a
no-op unless an equivalent review bot is configured.

## Detect / tag Jules

Jules is triggered by a **comment mention**, acted on by `.github/workflows/jules-trigger.yml`.

```bash
# Already mentioned on the PR? (look at issue/PR comments, NOT reviews)
gh pr view <N> --comments | grep -i 'google-labs-jules'
# or structured:
gh api repos/{owner}/{repo}/issues/<N>/comments \
  --jq '.[] | select(.body | test("google-labs-jules")) | {user: .user.login, body}'

# Tag Jules
gh pr comment <N> --body "@google-labs-jules please review this PR"

# Did the trigger land? The workflow adds a 👀 reaction to the triggering comment.
gh api repos/{owner}/{repo}/issues/comments/<comment-id>/reactions \
  --jq '.[] | .content'    # expect "eyes"

# GitLab equivalent (mention/note)
glab mr note <N> --message "@google-labs-jules please review this PR"
```

### Jules feedback shows up as (poll for all three)

```bash
# 1. Comments from Jules / its personas (Forge, Bolt, Palette, Sentinel)
gh api repos/{owner}/{repo}/issues/<N>/comments \
  --jq '.[] | select(.user.login | test("jules|forge|bolt|palette|sentinel"; "i"))'

# 2. New commits pushed to the PR branch
gh pr view <N> --json commits --jq '.commits[-3:]'

# 3. A separate linked PR opened by Jules
gh pr list --search "head:jules" --json number,title,headRefName
```

Trust gate: only a comment from an OWNER / MEMBER / COLLABORATOR triggers Jules
(the workflow's `author_association` check). As the PR author you normally
qualify. If no 👀 appears within a few minutes, the mention may not have passed
the gate — surface this and let the user post it from a trusted account.

## Fetch review feedback

Routing findings to fixes is the job of the **`address-pr-comments`** skill —
invoke it rather than re-implementing. For reference, its three channels are:

```bash
gh api repos/{owner}/{repo}/pulls/<N>/comments    # inline code comments
gh api repos/{owner}/{repo}/pulls/<N>/reviews     # review bodies
gh pr view <N> --comments                         # issue-level discussion
```
