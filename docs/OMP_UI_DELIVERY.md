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
`.omp/ui-delivery/tasks/` and `.omp/ui-delivery/evidence/`. The builder uses
only `read`, `grep`, `glob`, `ui_apply_patch`, and `ui_run_check`; the reviewer
uses only `read`, `grep`, `glob`, and `ui_capture`. Neither may spawn agents.

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
  separate output paths for every check; and
- capture recipes naming every evidence artifact.

Checks cannot receive a raw command. Their outputs must not overlap candidate
paths, `.git`, `.omp`, `secrets`, or a forbidden policy path. Docker recipes
also require a digest-pinned image.

The coordinator computes the canonical authorization digest over the approved
policy projection (`task_id`, design revision, path rules, checks, captures,
model route, and any Stitch grant) and supplies **that exact value** to the OMP
process as `UI_DELIVERY_APPROVED_TASK_SHA256`. A repository task cannot approve
itself. Do not hash formatted task JSON, expose credentials, or let the builder
supply or change the environment value. Any policy-relevant edit requires a new
digest and a new authorization.

## Run the lifecycle

1. Preflight the linked package and tools. Missing constrained tools block the
   task; there is no unrestricted substitute.
2. Move the approved task to `approved`, inject the external digest, and give
   it only to `ui-builder`.
3. The builder patches only allowed paths and records the resulting candidate
   revision and hash. It runs only named approved checks.
4. Move the exact candidate to `candidate_ready`/`reviewing`; `ui-reviewer`
   reads that revision and hash, captures declared evidence, and returns its
   strict review schema.
5. An accepted review becomes `verified` only after current checks and captures
   are bound to the same task, digest, design, candidate revision/hash, and
   model route. Authorized repair is limited to two cycles; the third open
   cycle is `blocked`.

`verified` means the task is accepted, the current candidate hash still
matches, every current-digest check's **latest attempt** completed verified, and
every capture has a current complete artifact hash. Treat a status with
`verified: false`—including the task outcome `unverified`—as
**evidence_unverified**, not as a pass. Skipped, unavailable, stale, timed-out,
or failed evidence cannot be promoted. `failed` is a failed check or review;
`blocked` covers authorization, recovery, or unresolved repair limits.

## Verifier and sandbox boundaries

A trusted verifier entrypoint must live outside `allowed_paths`; it treats the
candidate as data. If a check executes candidate code, run it in a separate
sandbox that has no permission to write the check result or evidence location;
the trusted verifier alone records results. This prevents a candidate from
turning its own output into evidence.

Checks use approved fixed argv and an OS sandbox. On macOS, the residual
compatibility scope includes `mach-lookup` and `file-read-metadata`; it is not a
general read grant. Content reads remain limited to the repository, approved
runtime/executable dependencies, scratch space, and required system paths; the
policy masks `.git`, `.omp`, `secrets`, and forbidden paths.

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

## Harness boundaries

| Harness | Supported surface |
| --- | --- |
| Claude | Portable skills and native plugin validation; not the constrained OMP agents or extension. |
| Codex | Portable skills and strict agent/output schemas; not the constrained OMP agents or extension. |
| OMP | Package-local agents, extension, roles, digest gate, sandbox checks, and evidence status. |

The role bindings are package-local overlays. Do not mutate global role
configuration, and do not enable model fallback to make a route run.
