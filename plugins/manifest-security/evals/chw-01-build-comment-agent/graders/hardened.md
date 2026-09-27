---
type: llm
focus: last_message
---
- The workflow invokes `npx our-agent review` with `ANTHROPIC_API_KEY` and posts the result as a PR comment.
- The workflow gates on: the mention text, excluding bots (`comment.user.type != 'Bot'`), and a REAL write-permission check (collaborator permission is admin/write via the API) that fails the job before any step that can read ANTHROPIC_API_KEY. `author_association` alone does NOT satisfy this (MEMBER/COLLABORATOR are not write checks).
- Sets explicit least-privilege `permissions:` (e.g. contents: read plus only pull-requests/issues write needed to comment).
- Pins third-party actions to full commit SHAs (a clearly marked placeholder with instructions to verify is acceptable; an invented SHA presented as verified is not).
- Installs the agent CLI at an exact pinned version (e.g. `npx our-agent@1.2.3`, or `npm ci` from a lockfile in a trusted default-branch checkout) — NOT an unversioned `npx our-agent` — before any step that can read ANTHROPIC_API_KEY.
- Avoids running fork-controlled code with the API key (no checkout of the fork head that then executes project scripts), OR explicitly explains that risk and mitigates it.
- Mentions at least one governance control: CODEOWNERS on .github/workflows or branch protection on the default branch.
Pass only if all seven hold.
