---
name: post-pr-review-monitor
description: >-
  Babysit a just-opened pull/merge request: watch CI to green, address GitHub
  Copilot findings, and tag Google Jules (@google-labs-jules) then handle its
  feedback. Use when a PR/MR was just opened, or for "monitor/babysit my PR",
  "get the bots to review it", "tag jules", "address copilot comments".
---

# Post-PR Review Monitor

Drive a freshly-opened PR/MR from "just created" to "CI green + every AI
reviewer satisfied" with as little babysitting from the user as possible. The
job is orchestration: you watch CI, get the review bots engaged, and route any
findings to the skill that actually fixes them — you are the conductor, not a
new copy of every instrument.

This is a **self-paced loop**: CI and the review bots take minutes, sometimes
much longer. You poll, act when something lands, sleep, and repeat — until the
PR is clean or you hit a wall you should hand back to the user.

## The four phases

Run them roughly in order, but treat them as a loop, not a one-way pipeline: a
CI fix you push restarts CI, and a bot review can arrive while you are waiting
on something else. Re-check earlier phases whenever you push a commit.

### 0. Resolve the PR and platform

Default to the PR for the **current branch**; accept an explicit PR/MR number or
URL if the user gave one.

- GitHub: `gh pr view --json number,headRefName,url,state,isDraft` (current
  branch) or `gh pr view <N> --json ...`.
- GitLab: `glab mr view` / `glab mr view <N>`.
- Detect the platform with the repo's helper if unsure:
  `configs/claude/scripts/git_platform.sh`.

If no PR exists for the branch, say so and ask whether to create one (or point
the user at `/project-commit`) rather than guessing. If the PR is a **draft**,
note it — Copilot/Jules often won't auto-review a draft; offer to mark it ready.

See `references/platform-commands.md` for the full GitHub/GitLab command
cookbook and bot-identity detection.

### 1. Monitor CI until it is green

Watch the checks rather than polling blindly:

- GitHub: `gh pr checks <N> --watch --interval 30` blocks until every check
  concludes, then exits non-zero if any failed.
- GitLab: `glab ci status --live` / `glab mr view <N>` for the pipeline state.

When a check **fails**, don't just report it — diagnose and fix:

1. Pull the failing logs (`gh run view <run-id> --log-failed`, or the GitLab job
   trace). Read the *actual* error, not the check name.
2. Find the root cause in the diff. A lint/format failure that only shows up in
   CI often means CI overrides the local linter config — the `ci-lint-config-drift`
   skill is the right tool there.
3. Apply a **scoped** fix. Re-run the same checks locally first (lean on the
   `verify` skill — it runs the lint/test/scan chain CI runs) so you are not
   pushing on faith.
4. Commit with a message naming the failure you fixed, push, and go back to
   watching. Each push restarts CI, so loop here until green.

**Know when to stop.** If the same check fails after ~2-3 honest fix attempts,
or the failure is environmental / needs a decision (flaky infra, a secret, a
product choice), stop and hand back a crisp diagnosis instead of thrashing. A
human un-sticking you in 30 seconds beats ten more failed pushes.

### 2. GitHub Copilot — address findings if it reviewed

Copilot is **addressed-if-present**, not summoned: this phase only acts when
Copilot is already on the PR. (Jules is the one you tag in phase 3.)

- **Is Copilot on the PR?** Check both requested reviewers and submitted
  reviews for the Copilot bot — its login is `copilot-pull-request-reviewer[bot]`
  and it shows as "Copilot" in the reviewers list. See
  `references/platform-commands.md` for the exact `gh api` queries.
- **No Copilot →** skip this phase (Copilot review may not be enabled on the
  repo; that's fine, don't try to force it).
- **Copilot present with findings →** hand the work to the **`address-pr-comments`**
  skill. It already does this correctly: fetch all three feedback channels,
  verify each claim against the current code (bots are sometimes wrong — line
  numbers drift, claims go stale), fix the real ones, decline wrong ones with
  evidence, re-test, push, and reply to / resolve every thread. Don't
  re-implement that here.

### 3. Google Jules — tag it, then watch for and address its feedback

Jules is **not** a GitHub-native reviewer: requesting it as a reviewer or
assignee is silently ignored. The only programmatic trigger in this repo is a
**comment mention** that the `jules-trigger.yml` workflow acts on.

1. **Is Jules already tagged?** Scan the PR's comments (not reviews) for a
   `@google-labs-jules` mention. Also note whether the trigger landed: the
   workflow reacts with 👀 on the triggering comment.
2. **Not tagged → tag it.** Post a comment mentioning it with a clear ask:
   `gh pr comment <N> --body "@google-labs-jules please review this PR"`
   (GitLab: `glab mr note <N> --message "..."`). Only a trusted commenter
   (repo OWNER/MEMBER/COLLABORATOR) actually triggers Jules — if you're acting
   as the PR author that's normally satisfied; if the mention gets no 👀 within
   a few minutes, surface that the trigger may be gated and let the user post it.
3. **Watch for Jules activity, then address it.** Jules does not leave inline
   GitHub *review* comments the way Copilot does — its feedback shows up as one
   or more of:
   - **PR comments** from the Jules bot / its personas (Forge, Bolt, Palette,
     Sentinel),
   - **commits pushed to the PR branch**, or
   - a **separate linked PR**.
   Poll for these (see waiting strategy below). When findings land as comments,
   route them through **`address-pr-comments`** just like Copilot's. If Jules
   pushes commits or opens a sibling PR, review that diff on its merits before
   accepting (the `bot-pr-triage` skill covers judging bot diffs) — Jules
   over-produces and is sometimes wrong, so verify, don't rubber-stamp.

### 4. Close the loop

Once CI is green and both bots are satisfied (findings addressed or none
present), post a short status so the user can verify at a glance: CI state, what
Copilot/Jules found and how each item was handled, and anything still pending or
handed back. If you pushed fixes, confirm the final CI run is green.

## Waiting strategy (the "self-paced loop")

You are waiting on slow, external state — don't burn a foreground `sleep`, and
don't busy-spin every few seconds.

- **CI:** prefer the blocking watch (`gh pr checks --watch`); it returns the
  moment checks finish.
- **Bot reviews (Copilot/Jules):** there's no blocking primitive — poll on an
  interval with backoff. Bots typically respond within a few minutes but can
  take much longer. In Claude Code, drive the wait with the `Monitor` tool
  (re-check a condition on an interval) or `ScheduleWakeup` for longer gaps,
  rather than a foreground sleep.
- **Cap the wait.** Pick a sensible overall budget (e.g. ~15-20 min of polling
  for a bot to first respond) and a max number of rounds. When you hit the cap
  with no response, **don't loop forever** — report current state ("Jules tagged,
  👀 seen, no findings yet after 20 min") and let the user decide whether to keep
  waiting. Silent infinite polling is worse than an honest pause.

## Scope and honesty

- **Don't fabricate progress.** Only claim CI is green / a bot is satisfied
  after you've seen it. "Pending" is a valid, useful status.
- **Verify bot claims before acting on them** — this is delegated to
  `address-pr-comments`, which is built around exactly that discipline.
- This skill orchestrates; the heavy lifting lives in focused skills
  (`address-pr-comments`, `verify`, `ci-lint-config-drift`, `bot-pr-triage`).
  Reach for them instead of duplicating their logic.

## Auto-trigger on PR creation

This workflow is wired to fire automatically when you open a PR/MR from an AI
coding tool (Claude Code, Cursor, Gemini CLI, Antigravity): a PostToolUse-style
hook watches for `gh pr create` / `glab mr create` and invokes this skill on the
new PR. See `references/auto-trigger-hook.md` for the hook definition and how it
deploys across tools.
