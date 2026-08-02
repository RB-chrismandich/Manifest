# Platform command cookbook

GitHub (`gh`) and GitLab (`glab`) commands for each phase, plus how to detect
the AI review bots. Read this when you need the exact invocation.

Bot identities used below (`author_login`, `mention`, `identified_by`) come
from `../../runtime/config/review_bots.json` — the registry, not this file, is
the source of truth if a login ever changes. Commands here embed the
registry's current values; re-check the registry, not just this cookbook, when
a detection query stops matching.

## Contents

- [Resolve PR + platform](#resolve-pr--platform)
- [CI / pipeline status](#ci--pipeline-status)
- [Detect Copilot](#detect-copilot)
- [Detect / tag Jules](#detect--tag-jules)
- [Fetch review feedback](#fetch-review-feedback)

## Resolve PR + platform

```bash
# Platform detection (repo helper): prints github | gitlab | git
../../runtime/bin/git_platform.sh

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

GitHub Copilot code review posts as a bot. Identify it by login, not display
name — `review_bots.json`'s `copilot.author_login`, verified via `gh api
.../pulls/<N>/reviews` against real reviews on this repo (PRs #533-#563).

```bash
# Is Copilot a requested reviewer?
gh pr view <N> --json reviewRequests \
  --jq '.reviewRequests[] | select(.login // .name | test("[Cc]opilot"))'

# Has Copilot submitted a review? (bot login: copilot-pull-request-reviewer[bot],
# i.e. review_bots.json -> bots.copilot.author_login)
gh api repos/{owner}/{repo}/pulls/<N>/reviews \
  --jq '.[] | select(.user.login | test("copilot")) | {state, id, body}'
```

- Login to match: `copilot-pull-request-reviewer[bot]` (case-insensitive
  `copilot` substring is a safe filter).
- If neither query returns anything, Copilot review is not on this PR — skip the
  Copilot phase. Do not try to add it; whether it runs is a repo/org setting
  (`review_bots.json`'s `copilot.invoke: automatic`).

GitLab: GitHub Copilot PR review is GitHub-specific; on GitLab this phase is a
no-op unless an equivalent review bot is configured.

## Detect / tag Jules

Jules is triggered by a **comment mention** (`review_bots.json`'s
`jules.mention`), acted on by `.github/workflows/jules-trigger.yml`. Its login
(`jules.author_login` = `google-labs-jules[bot]`) was confirmed via its own
greeting comment on real PRs (#580, #581) — `gh api
.../issues/<N>/comments`.

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
# 1a. Comments from the Jules bot account itself
gh api repos/{owner}/{repo}/issues/<N>/comments \
  --jq '.[] | select(.user.login | test("jules"; "i"))'

# 1b. Sibling PRs opened under a Jules persona (palette/bolt — see review_bots.json;
# these have NO distinct bot login, so match by title/branch prefix, not author).
# NOTE: GitHub search ANDs repeated qualifiers, so two `in:title` clauses would
# require a single PR title containing BOTH strings (impossible) — use `OR`.
gh pr list --search "in:title 🎨 Palette: OR in:title ⚡ Bolt:" \
  --json number,title,headRefName,author

# 2. New commits pushed to the PR branch
gh pr view <N> --json commits --jq '.commits[-3:]'

# 3. A separate linked PR opened under a Jules persona branch (registry
# branch_prefix values: palette/, bolt/). Same AND-vs-OR pitfall as 1b above.
gh pr list --search "head:palette/ OR head:bolt/" --json number,title,headRefName
```

Trust gate: only a comment from an OWNER / MEMBER / COLLABORATOR triggers Jules
(the workflow's `author_association` check). As the PR author you normally
qualify. If no 👀 appears within a few minutes, the mention may not have passed
the gate — surface this and let the user post it from a trusted account.

## Fetch review feedback

Routing findings to fixes is the job of the **`pr-address-comments`** skill —
invoke it rather than re-implementing. For reference, its three channels are:

```bash
gh api repos/{owner}/{repo}/pulls/<N>/comments    # inline code comments
gh api repos/{owner}/{repo}/pulls/<N>/reviews     # review bodies
gh pr view <N> --comments                         # issue-level discussion
```
