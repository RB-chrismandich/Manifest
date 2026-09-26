# Git Platform Reference

> Native `git`, `gh`, and `glab` operations for GitHub, GitLab, and plain Git
> repositories. `git_platform.sh` remains the deterministic provider detector.

## Platform detection

```bash
~/.claude/scripts/git_platform.sh [remote_name]
```

It prints `github`, `gitlab`, or `git`. Its precedence is:

1. `MANIFEST_GIT_PLATFORM` (`github`, `gitlab`, or `git`);
2. the explicit `remote_name`;
3. `MANIFEST_GIT_REMOTE`;
4. `origin`.

Skills may inspect `git remote get-url` directly, but must use the same
override and remote precedence. Keep the chosen repository and host for every
read, reply, mutation, and verification—especially for forks and enterprise
hosts. Do not fall back to the current checkout after a target is known.

Plain Git and unknown custom hosts allow local `git` operations only. Do not
guess a forge from which executable happens to be installed; request explicit
provider context for forge operations.

Authentication belongs to `gh` or `glab`. A missing executable,
authentication, permission, or nonzero native command is an actionable
failure, never an empty queue or successful mutation. An existing hook may
intentionally report that failure while remaining fail-open; preserve that
hook's policy.

## Native provider commands

Use the native CLI directly at the call site; there is no platform-agnostic
operations wrapper.

| Behavior | GitHub | GitLab |
| --- | --- | --- |
| Read/list/create/close issues | `gh issue view/list/create/close` | `glab issue view/list/create/close` |
| Edit issue description/labels | `gh issue edit N --body TEXT --add-label LABEL --remove-label LABEL` | `glab issue update N --description TEXT --label LABEL --unlabel LABEL` |
| Comment on issue | `gh issue comment N --body TEXT` | `glab issue note N --message TEXT` |
| Create PR/MR | `gh pr create --title TITLE --body TEXT --base BASE --head BRANCH` | `glab mr create --title TITLE --description TEXT --target-branch BASE --source-branch BRANCH --yes` |
| Create draft PR/MR | add `--draft` | add `--draft` |
| Read/list/diff/close/reopen PR/MR | `gh pr view/list/diff/close/reopen` | `glab mr view/list/diff/close/reopen` |
| Edit PR/MR | `gh pr edit N --body TEXT --base BASE` | `glab mr update N --description TEXT --target-branch BASE` |
| General PR/MR reply | `gh pr comment N --body TEXT` | `glab mr note N --message TEXT` |
| Close with explanation | `gh pr close N --comment TEXT` | `glab mr note N --message TEXT`, then `glab mr close N` |
| Approve | `gh pr review N --approve` | `glab mr approve N` |
| Create label | `gh label create NAME --color COLOR --description TEXT --force` | `glab label create --name NAME --color '#RRGGBB' --description TEXT` |

Do not use approval as a substitute for a comment or request-changes review.
For GitLab JSON, request `--output json` and consume actual fields such as
`iid`, `description`, `source_branch`, `target_branch`, and `state`; GitHub
JSON field names are not portable.

GitLab issues are open by default. Map closed/all listing explicitly to
`--closed`/`--all`, and use `--per-page` only where a bounded listing needs a
limit. For a GitLab issue body held in a file, use:

```bash
glab api -X POST projects/PROJECT/issues -f title="$title" \
  -F description=@"$body_file" -f labels=planned
```

Consume `.iid`. When API query fields are supplied, pass `-X GET` for reads;
otherwise `glab api` defaults to POST. `glab api` supports `--paginate`, `-X`,
`-f`, and typed `-F`; process returned JSON with `jq`. `glab mr create --head`
selects a head repository, not a branch—use `--source-branch`.

`gh pr view` does not expose a `reviewThreads` JSON field. Review-thread
enumeration and resolution require GitHub GraphQL, and GitLab discussion
resolution requires the Discussions API; see `pr-address-comments`.
