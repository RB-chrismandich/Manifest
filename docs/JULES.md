# Jules integration

Jules is an optional remote GitHub task backend for Manifest's `/delegate`.
Its official CLI runs cloud sessions; it does not inherit local harness settings.

## Setup

```bash
./bootstrap.sh --enable-jules
jules login
jules remote list --repo
```

Bootstrap installs `@google/jules@0.1.42` when absent and checks authentication.
An existing authenticated installation is preserved. Unattended setup does not
open a login browser. The vendor CLI owns credential storage and refresh;
Manifest never copies tokens. Verify persistence with a second repository listing
from a new process. Login can still expire or be revoked by the provider.

Authorize the Jules GitHub App for the repository separately. The CLI listing
must include the desired `OWNER/REPO`. Empty listings and authentication errors
(even with exit zero) are reported as unverified, not ready.

## Delegate a remote task

Use the installed `/delegate` skill, or from this checkout:

```bash
python3 plugins/manifest-delegate/scripts/delegate.py setup --backend jules
python3 plugins/manifest-delegate/scripts/delegate.py task --backend jules \
  --remote-write --repo OWNER/REPO --remote-base provider-selected --task-file TASK.md
python3 plugins/manifest-delegate/scripts/delegate.py status JOB_ID --wait --timeout 600
python3 plugins/manifest-delegate/scripts/delegate.py pull JOB_ID
```

Review the saved artifact before `delegate.py apply JOB_ID`. Apply requires a
clean working tree with a matching GitHub origin. No push or merge is automatic.

The CLI cannot pin a branch. `--remote-base provider-selected` acknowledges that
Jules chooses its remote base; current branch, local commits and uncommitted files
are not implicitly sent. Use the Jules UI when an exact branch is required.
Submission returns a pending job, not completed code. Resume, remote cancellation,
model fallback and read-only review are unsupported. Use the session URL for
feedback, plan approval or stopping work. An uncertain submission is never retried
automatically because it may already be running remotely.

## Start from a GitHub issue

Apply `jules` (case insensitive) to an issue in a repository authorized for the
Jules App. Jules acknowledges on the issue and links its PR when finished.
Do not additionally submit the same issue through the CLI. PR monitoring handles
existing Jules feedback but does not label linked issues or summon Jules with a
comment. The former custom mention-trigger workflow has been removed; it no
longer requires `JULES_API_KEY`. Existing repository secrets are not deleted by
this change and should only be removed after checking other consumers.

## Verification boundaries

Measured 2026-09-07 on CLI 0.1.42: two fresh processes listed authorized
repositories/sessions; fetching a completed Manifest task returned a diff without
applying it. Submission acknowledgement format was inspected in the installed
binary (`Session created: <base>/session/<id>`). No new cloud task was launched
as part of development verification. Long-term token refresh is not simulated.

[Official CLI reference](https://jules.google/docs/cli/reference) ·
[Issue-label workflow](https://jules.google/docs/running-tasks/)
