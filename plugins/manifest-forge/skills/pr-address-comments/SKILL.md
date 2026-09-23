---
name: pr-address-comments
description: "Use when your open PR receives review feedback (inline comments, Copilot/CodeRabbit, review-body, issue discussion) — resolve every item truthfully: fix real issues, decline wrong ones with evidence, never mark resolved without a verified fix. Distinct from analysis-only pr-review."
---

# Address PR Review Comments

Resolve every piece of feedback truthfully. Ignore non-actionable service notices.
Never call a thread resolved because a comment says “Resolved”.

## Procedure

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
5. **Publish exact replies.** Reply in the eligible thread/discussion with the
   fix SHA and verification evidence, or a rejection rationale and evidence.
   A disputed rejection remains open until accepted. Top-level review bodies
   and standalone comments get a linked reply and a summary disposition, but
   are `not applicable` for formal resolution.
6. **Resolve only verified eligible threads.** Re-read immediately before the
   resolution mutation. New actionable feedback must be addressed first.
   Already-resolved threads receive neither duplicate replies nor mutations on
   rerun when the same disposition/fix is recorded.
7. **Independently read back state.** A CLI nonzero, GraphQL `errors`, null or
   missing mutation data, permission error, or false/missing readback is
   `unresolved—resolution failed`; report its exact link and error. Re-enumerate
   all feedback once at completion. Newly arrived/unaddressed feedback remains
   outstanding; never report “all addressed” merely because the first list was
   exhausted.

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

Re-read the thread, then resolve it only after the reply succeeds:

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

## Completion publication

Post one summary disposition table with links, claim, action or rejection,
fix SHA, verification evidence, and formal resolution state. A top-level
review body or standalone comment is marked `addressed — not applicable` for
formal resolution; a failed resolve is marked `unresolved—resolution failed`.

> Absorbed: address-pr-review-comments, address-review-comments (2026-06)
