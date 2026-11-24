---
name: pr-address-comments
description: "Use when your open PR receives review feedback (inline comments, Copilot/CodeRabbit, review-body, issue discussion) — resolve every item truthfully: fix real issues, decline wrong ones with evidence, never mark resolved without a verified fix. Distinct from analysis-only pr-review."
---

# Address PR Review Comments

**Platform closure is mandatory.** Review and disposition every feedback item,
and publish a how/why explanation directly on the originating PR/MR platform
for every addressed item. After actionable feedback is fixed, verified, and
successfully published, explicitly resolve every eligible thread/discussion
using that platform's native resolution UI or API, then independently read back
the final state. Local edits, commits, disposition tables, chat replies, or
text saying “resolved” do not publish a platform reply or resolve a thread.
Each reply must state what changed and why it satisfies the feedback (or give
an evidence-backed rejection rationale); include the fix SHA and verification
evidence when applicable. Reply in the exact originating thread/discussion
where supported; otherwise post a linked platform reply.

Resolve every piece of feedback truthfully. Ignore non-actionable service notices.
Never call a thread resolved because a comment says “Resolved”.

## Procedure

0. **Check for an idle human block before spawning work.** For each managed PR,
   run `<plugin root>/runtime/bin/pr_merge_loop.sh address-status N`. This makes
   one read-only observation and compares it with the existing repository-scoped
   `fp_<scope-hash>_<PR>.json` record (`observed_at` is the last handled check).
   On `blocked on human: #N`, emit only that line for the PR and stop if all
   PRs are blocked; do not spawn subagents, poll again, or resolve threads.
   `actionable: #N` admits normal work; new/edited feedback changes the
   fingerprint even if its timestamp predates the last check. Missing state is
   actionable, never proof of idle; failed observation is unverified.
   The actual `pr_merge_loop.sh run` driver stops immediately when all managed
   PRs have the persisted `hand-human` disposition. Across invocations it
   compares each PR's existing fingerprint-state `observed_at`; after three
   identical complete no-progress turns it emits `loop idle: waiting on human`
   once. Each later invocation still makes one observation per PR and prints
   its blocked line, but does not repeat the idle announcement. Changed
   feedback reopens normal work; incomplete observation never advances idle.
   This outer three-turn threshold is independent of both the five-empty-pass
   inner stop and the three-revision limit. Reinvoke it to observe new feedback.
   To establish a human-only disposition, first capture
   `pr_merge_loop.sh address-status N --json`, then perform the final feedback
   enumeration below. If only human work remains, pass that JSON's fingerprint
   to `pr_merge_loop.sh record-human-blocked N FINGERPRINT`. A changed
   observation refuses the write and requires re-enumeration; success persists
   the per-PR check timestamp without resolving any thread. Never record a
   failed/unavailable review as a human-only disposition.
1. **Identify the provider and immutable target.** Use the configured override or
   the selected remote as documented in `runtime/references/git-platform.md`.
   Record the provider, PR/MR number, repository/project target, and host. Do
   not default API calls back to the current checkout after a target is known.
2. **Build a session disposition table.** For every item, record provider,
   PR/MR, thread/discussion ID, comment/note ID, URL, resolvability and current
   resolution state, actionable claim, disposition, fix SHA, verification
   evidence, and final resolution status. This is a working table, not a new
   persisted schema.
3. **Fetch all feedback, including every page.** Deduplicate by comment/note
   identity, never text. Preserve general discussion notes; only ignore GitLab
   system notices.
4. **Verify, triage, fix, and test.** Confirm each claim against current code;
   outdated line positions do not prove the claim fixed. Every actionable item
   in a resolvable thread must be fixed and verified before that thread can be
   resolved. If tests fail, a fix is unpublished, feedback is deferred, or a
   human disputes a rejection, reply truthfully and leave it unresolved.
5. **Publish exact platform replies.** Successfully publish a how/why reply on
   the PR/MR platform for each addressed item before attempting eligible
   resolution. Reply in the exact thread/discussion with the fix SHA and
   verification evidence, or an evidence-backed rejection rationale. A
   disputed rejection remains open until accepted. Top-level review bodies,
   standalone comments, and feedback without a formal thread get a linked
   platform reply and summary disposition; report `addressed — not applicable`
   for formal resolution when the provider has no native resolve capability.
   A chat response is never a substitute.
6. **Resolve only verified eligible threads.** Immediately before each
   resolution mutation, re-read the target thread/discussion and its feedback
   to detect new items. New actionable feedback must be addressed first. Resolve
   only after the platform reply succeeds and all actionable items in that
   thread are fixed, verified, and published. Already-resolved threads receive
   neither duplicate replies nor mutations on rerun when the same disposition/
   fix is recorded.
7. **Independently read back state.** A CLI nonzero, GraphQL `errors`, null or
   missing mutation data, permission error, or false/missing readback is
   `unresolved—resolution failed`; report its exact link and error. Re-enumerate
   all feedback once at completion. Newly arrived/unaddressed feedback remains
   outstanding; never report “all addressed” merely because the first list was
   exhausted. Do not report closure without independent platform readback.

## GitHub: complete feedback inventory and resolution

`gh pr view --json reviewThreads` is invalid: that JSON field is unsupported.
Use literal GraphQL queries and variables; never interpolate comment content
into a GraphQL document.

Enumerate threads, with `--paginate`:

```bash
gh api graphql --paginate -f query='query($owner:String!,$repo:String!,$pr:Int!,$endCursor:String) {
  repository(owner:$owner,name:$repo) {
    pullRequest(number:$pr) {
      reviewThreads(first:100,after:$endCursor) {
        nodes { id isResolved isOutdated viewerCanReply viewerCanResolve path line }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR"
```

For **each** thread, enumerate all nested comments separately:

```bash
gh api graphql --paginate -f query='query($thread:ID!,$endCursor:String) {
  node(id:$thread) {
    ... on PullRequestReviewThread {
      id isResolved viewerCanReply viewerCanResolve
      comments(first:100,after:$endCursor) {
        nodes { id databaseId url body author { login } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}' -f thread="$THREAD_ID"
```

Fetch review bodies and standalone issue comments independently, with all
pages, then deduplicate by their IDs:

```bash
gh api --paginate "repos/$OWNER/$REPO/pulls/$PR/reviews"
gh api --paginate "repos/$OWNER/$REPO/issues/$PR/comments"
```

After a verified fix, reply in the **thread** (not an individual numeric
comment ID). Pass body text as a CLI variable or `-F body=@FILE`:

```bash
gh api graphql -f query='mutation($thread:ID!,$body:String!) {
  addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread,body:$body}) {
    comment { id url }
  }
}' -f thread="$THREAD_ID" -f body="$BODY"
```

Re-read the thread immediately before resolving it, and resolve only after the
platform reply succeeds:

```bash
gh api graphql -f query='mutation($thread:ID!) {
  resolveReviewThread(input:{threadId:$thread}) { thread { id isResolved } }
}' -f thread="$THREAD_ID"
gh api graphql -f query='query($thread:ID!) {
  node(id:$thread) { ... on PullRequestReviewThread { id isResolved } }
}' -f thread="$THREAD_ID"
```

Only the second query proves resolution. `isOutdated` does not bypass claim
verification. Lack of `viewerCanReply`/`viewerCanResolve` is an explicit
unresolved permission outcome.

## GitLab: complete feedback inventory and resolution

Use a known numeric project ID or URL-encoded full path; use `:id` only after
verifying that the checkout is the target. Fetch both discussion and standalone
note channels, preserving discussion and note IDs:

```bash
glab api --paginate "projects/$PROJECT/merge_requests/$MR/discussions"
glab api --paginate "projects/$PROJECT/merge_requests/$MR/notes"
```

Ignore system notices, retain non-diff general discussion notes, and inspect
`resolvable` and `resolved` on notes. Reply to the exact eligible discussion,
then resolve it and read it back:

```bash
glab api -X POST "projects/$PROJECT/merge_requests/$MR/discussions/$DISCUSSION_ID/notes" -f body="$BODY"
glab api -X PUT "projects/$PROJECT/merge_requests/$MR/discussions/$DISCUSSION_ID" -F resolved=true
glab api "projects/$PROJECT/merge_requests/$MR/discussions/$DISCUSSION_ID"
```

Count the discussion resolved only when the readback confirms every resolvable
note is resolved. Absence of resolvable notes is not success. A Developer,
Maintainer, Owner, or author-of-change permission failure is reported and is
never bypassed.

## Other providers

Use the provider's native comment/reply and resolution capabilities; do not
invent endpoint examples or claim unsupported state. Publish the explanation
on the originating PR/MR platform and verify any available resolution state.
If formal resolution is unavailable, report `addressed — not applicable` and
link the platform reply rather than implying a thread was resolved.

## Completion publication

Post a final disposition summary on the PR/MR platform, not only in assistant
chat. Include links to each reply, claim, action or rejection rationale, fix
SHA, verification evidence, and formal resolution state confirmed by
independent readback. Top-level review bodies or standalone comments without a
formal resolve capability are `addressed — not applicable`; a failed resolve
or readback is `unresolved—resolution failed` and remains outstanding. Do not
claim all feedback addressed while any item is deferred, disputed, unpublished,
newly arrived, or otherwise unresolved.

> Absorbed: address-pr-review-comments, address-review-comments (2026-06)
