# OMP UI delivery

`stitch-design` 0.4.0 provides an OMP-only, bounded UI-delivery path. It is a
local package: link `plugins/stitch-design` through OMP's local-package linking
mechanism, then launch OMP in the repository being changed. The package's
`package.json` declares `extensions/ui-delivery-policy.ts`; do not copy that
extension, edit global roles, or enable a fallback route.

## Prerequisites

The target repository needs the linked package, the OMP `ui-builder` and
read-only `ui-reviewer` agents, and these extension tools:

| Tool | Approval | Purpose |
| --- | --- | --- |
| `ui_delivery_status` | read | Report task status and whether its evidence is current. |
| `ui_apply_patch` | write | Apply a non-destructive patch only under `allowed_paths`. |
| `ui_run_check` | exec | Run one named, approved fixed-argv check. |
| `ui_capture` | exec | Create only a declared evidence artifact. |

The task and evidence directories are repository-local:
`.omp/ui-delivery/tasks/` and `.omp/ui-delivery/evidence/`. The builder declares
only `read`, `grep`, `glob`, `ui_apply_patch`, and `ui_run_check`; the reviewer
declares only `read`, `grep`, `glob`, and `ui_capture`. Neither may spawn agents.
The extension independently enforces `@ui_code` for patch/build-check calls and
`@ui_review` for capture calls; agent tool declarations are not the security
boundary.

## Qualify the model route

Qualification takes an explicit OMP model catalog JSON; an overlay alone is not
proof that a model is available. From the repository root, run either command
with a catalog captured from the OMP instance that will run the task:

```sh
node plugins/stitch-design/runtime/model-qualification/qualify-models.mjs \
  --overlay plugins/stitch-design/runtime/model-qualification/astra.example.json \
  --catalog path/to/omp-astra-catalog.json --json

node plugins/stitch-design/runtime/model-qualification/qualify-models.mjs \
  --overlay plugins/stitch-design/runtime/model-qualification/local-only.example.json \
  --catalog path/to/local-catalog.json --json --local-only
```

The Astra overlay binds `designer`, `ui_code`, and `ui_review` to
`openai-codex/gpt-6-astra:high`; `retry.modelFallback` is `false`. Qualification
requires each selected catalog model to support the requested thinking level, a
128k context window, 16k output tokens, and image input for designer and
reviewer. The returned qualification hash records the resolved route.

For offline/local use, replace all three selectors in a copy of
`local-only.example.json` with catalog entries from exactly one or more of
`ollama`, `lmstudio`, or `llamacpp`, preserving the required capabilities. Run
with `--local-only`; it rejects cloud providers and requires
`mcp.enableProjectConfig` to remain `false`. This mode has no Stitch project
configuration.

## Prepare and authorize a task

Create a task JSON under `.omp/ui-delivery/tasks/` that satisfies
`plugins/stitch-design/skills/ui-delivery/references/task.schema.json`. Begin in
`draft`, then have the trusted coordinator approve a manifest containing:

- one `@ui_code` route, a design revision, narrow `allowed_paths`, and explicit
  forbidden policy paths;
- fixed `argv`, relative `cwd`, timeout, sandbox backend, result path, and
  separate output paths for every check;
- a `trusted_verifier` for every result-producing recipe: its
  `.omp/ui-delivery/verifiers/` path and exact `sha256:` digest; and
- capture recipes naming every evidence artifact.

Checks cannot receive a raw command. Their outputs must not overlap candidate
paths, `.git`, `.omp`, `secrets`, or a forbidden policy path. Docker recipes
also require a digest-pinned image.

The coordinator computes the canonical authorization digest over the approved
policy projection (`task_id`, design revision, path rules, checks, captures,
model route, and any Stitch grant) and supplies **that exact value** to the OMP
process as `UI_DELIVERY_APPROVED_TASK_SHA256`. A repository task cannot approve
itself. Do not hash formatted task JSON, expose credentials, or let an agent
supply or change the environment value. Any policy-relevant edit requires a new
digest and a new authorization. Lifecycle state, candidate identity, outcome,
repair count, and evidence references are deliberately outside that immutable
projection; switching from `@ui_code` to `@ui_review` still changes the digest
and requires fresh coordinator authorization.

## Run the lifecycle

1. Preflight the linked package and tools. Missing constrained tools block the
   task; there is no unrestricted substitute.
2. Move the approved task to `approved`, set `model_route` to `@ui_code`,
   inject the builder digest, and give it only to `ui-builder`.
3. The builder patches only allowed paths and records the resulting candidate
   revision and hash. It may run named build checks only. A check referenced by
   a capture recipe is capture-only and `ui_run_check` rejects it.
4. The trusted coordinator confirms the current candidate hash and the latest
   builder-check attempts under the builder digest. It then atomically changes
   the exact task to `reviewing` with `model_route: "@ui_review"`, computes the
   new reviewer digest, and starts a separate reviewer process with that digest.
   The old builder digest cannot authorize capture.
5. `ui-reviewer` reads the exact revision/hash, invokes only declared capture
   recipes, inspects their artifacts, and returns the strict review schema.
6. The coordinator validates the review schema and candidate identity before
   mapping an accepted verdict to `accepted`/`verified`. Authorized repair is
   limited to two cycles; the third open cycle is `blocked`.

`verified` means the task is accepted on `@ui_review`, the current candidate
hash still matches, every unreferenced build check's latest attempt is verified
under the equivalent `@ui_code` policy digest, and every declared capture's
latest attempt and current complete artifact hash match the reviewer digest.
Later wrong-route, wrong-digest, unfinished, or failed attempts invalidate the
corresponding evidence. Treat `verified: false`—including task outcome
`unverified`—as **evidence_unverified**, not as a pass. Skipped, unavailable,
stale, timed-out, or failed evidence cannot be promoted. `failed` is a failed
check or review; `blocked` covers authorization, recovery, or repair limits.

## Verifier and sandbox boundaries

Evidence-producing recipes run only when their declared verifier is a regular,
non-symlink file below `.omp/ui-delivery/verifiers/`, outside every
`allowed_paths` entry, present in fixed `argv`, and byte-for-byte equal to its
approved SHA-256. The runtime rejects candidate-path executables, verifier
paths that escape the protected root, and digest mismatches before mounting any
output location. Docker masks `.omp` then remounts only the verified verifier
root read-only; candidate files are read-only inputs.

The verifier treats the candidate as data and is the only code permitted to
author declared results or artifacts. Arbitrary candidate unit-test commands
are not trusted evidence producers: if candidate code must execute, it runs in
a separate sandbox with no result or artifact write mount, and the hash-bound
verifier records the outcome.

Checks use approved fixed argv and an OS sandbox. Docker checks require a
digest-pinned image and run with no network, a read-only root filesystem, the
host caller's non-root UID/GID, fixed non-secret environment, exact output and
scratch mounts, and protected-path masks. On macOS, `sandbox-exec` has residual
compatibility scope for `mach-lookup` and `file-read-metadata`; it is not a
general read grant. Content reads remain limited to the repository, approved
runtime/executable dependencies, scratch space, and required system paths;
`.git`, `.omp`, `secrets`, and forbidden paths remain masked except for the
verified, read-only verifier root.

## Deterministic release pilot

Live Stitch credentials were unavailable for this release. The release E2E is a
hand-authored, deterministic two-route fixture, not a publish or live-Stitch
claim. Prepare isolated case repositories outside the worktree with:

```sh
node tests/fixtures/ui-delivery-consumer/prepare.mjs /absolute/temporary-parent
```

The parent argument must be absolute. The command creates it as needed and
prints one JSON launch record containing two case repository/task/external
approval-digest triples. Use those values to start isolated OMP runs; do not
place the generated task or digest in this repository.

The pilot's visual capture runs Chromium with JavaScript disabled inside the
digest-pinned `ghcr.io/open-webui/computer` image declared by the fixture. The
outer container remains networkless, read-only, non-root, and limited to exact
result mounts. Both routes must complete separate Astra builder and reviewer
runs and finish with `ui_delivery_status.verified: true`; fixture preparation
alone is not release evidence.

## Harness boundaries

| Harness | Supported surface |
| --- | --- |
| Claude | Portable skills and native plugin validation; not the constrained OMP agents or extension. |
| Codex | Portable skills and strict agent/output schemas; not the constrained OMP agents or extension. |
| OMP | Package-local agents, extension, roles, digest gate, sandbox checks, and evidence status. |

The role bindings are package-local overlays. Do not mutate global role
configuration, and do not enable model fallback to make a route run.
