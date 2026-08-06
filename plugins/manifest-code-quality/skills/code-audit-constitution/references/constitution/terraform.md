<!-- doc-type: reference -->
# Code Constitution — Terraform / OpenTofu Annex

> Applies the universal articles to declarative infrastructure, where the unit of reuse is a module, the
> boundary contract is a typed variable, and a mistake changes production rather than a return value.

**Last Updated**: 2026-07-29
**Audience**: AI assistants and contributors writing Terraform / OpenTofu
**Purpose**: Give `.tf` and `.tfvars` changes the same pre-write doctrine as source code, in HCL terms

Universal articles: [code-constitution.md](../code-constitution.md).
Adjacent machine copy: `../../config/code_constitution.json` (`languages.terraform`).
Post-write audit of an existing tree — security posture, blast radius, state management: `/manifest-code-quality:terraform-refactor`.

## Toolchain

The `terraform_*` pre-commit hooks are configured but dormant — this repo has no real `.tf` files yet, and
`types_or: [terraform]` arms all four the moment one lands. The `tofu` binary substitutes for `terraform` in
every command below. Start from the bundle-local `project-scaffold` Terraform
templates — `versions.tf.tmpl`, `main.tf.tmpl`, and a
`.tflint.hcl` already carrying the `recommended` preset — rather than re-deriving them.

| Role | Tool | Rule |
|---|---|---|
| Manifest | `versions.tf` | The single place `required_version` and `required_providers` are declared, per module. |
| Packager | `terraform` | `init`/`plan`/`apply` only; no wrapper script re-implements what the CLI already does. |
| Formatter | `terraform fmt` | The only formatter. Run `-recursive`; never hand-align HCL. |
| Linter | `tflint` | Configured once in `.tflint.hcl` (`recommended` preset); suppress per-rule inline with a reason. |
| Typechecker | `terraform validate` | Runs after `init`; proves syntax and type wiring, never behavior. |
| Tests | `terraform test` | `*.tftest.hcl` beside the module it covers; the only in-repo behavior gate. |
| Audit | `trivy` | `trivy config` on the module tree. `tfsec` is deprecated (merged into Trivy, 2024) — do not add it. |
| Lockfile | `.terraform.lock.hcl` | Committed for every root module; regenerated with `terraform providers lock`, never hand-edited. |

## Size ceilings (CON-002)

| Unit | Ceiling | Split when |
|---|---|---|
| `.tf` file | 300 lines | A second resource family appears in the file. |
| Nested block depth | 4 | A `dynamic` block nests inside another `dynamic` block. |
| Duplicated block | 10 lines | The same block shape appears a third time, in any file. |
| Inline payload literal | 12 lines | A heredoc, `jsonencode`, or map literal crosses it. |
| Class / function / parameters / methods per class | 0 — not evaluated | Terraform has no such units; `C-SIZE` skips them entirely. |

Split first by resource family within the module — `network.tf`, `iam.tf`, `data.tf` — because a `.tf` file is
only a container and the parser concatenates the directory anyway. The real seam is the module boundary: when a
group of resources has one owner, one lifecycle, and a nameable purpose, it becomes `modules/<name>/`. A root
module holds a backend, provider configuration, module calls, and the wiring between them — nothing else; if a
root module contains resource blocks worth 300 lines, the module extraction is overdue, not the file split.

## Payload extraction map (CON-004)

| Payload | Lives in | Loaded by |
|---|---|---|
| IAM / bucket / KMS policy JSON | `templates/<name>.json.tftpl` | `templatefile()`, or a `*_policy_document` data source |
| Cloud-init / `user_data` scripts | `templates/user_data.sh.tftpl` | `templatefile()` at the resource attribute |
| Container or task definitions, k8s manifests | `templates/<name>.json.tftpl` | `templatefile()` |
| Static blobs with no interpolation (certs, configs) | `files/<name>.<ext>` | `file()` |
| Region / environment lookup maps | `files/<name>.json` or `<env>.tfvars` | `jsondecode(file(...))` or a typed `var` |

**Legitimately inline**: a `jsonencode({...})` of a few keys that reads at a glance; the `tags` map; a one-line
`user_data` that invokes a package manager; `description` and `error_message` strings. Prefer `jsonencode()` over
a heredoc for any inline JSON — it escapes correctly and fails at plan time on a malformed structure, where a
heredoc ships the typo to the provider.

## Article annexes

### CON-001 — Search before you write

- Search `modules/` and the registry (private first, then public) before writing raw resource blocks for
  anything conventional — network, cluster, log bucket.
- Before hardcoding an ID, ARN, AMI, or zone, look for the data source that resolves it.
- Extend an existing module with an optional typed input; a second module with a near-identical name is a fork,
  and the two will diverge on the next provider upgrade.

### CON-003 — Third time, centralize

- Duplicated resource blocks across `dev/`, `staging/`, and `prod/` are this language's canonical DRY failure.
  The fix is one module plus one `.tfvars` per environment — never a copied directory with three edited values.
- Copy-pasted resources within a file that differ only by name become one resource with `for_each` over a typed
  map. Copy-paste across files that differ by more than name becomes a child module.
- Extract behavior, not shape: two security groups that look alike but are governed by different teams stay
  apart, because they change for different reasons.
- Environments differ by input values only. When one environment needs a resource another does not, that is a
  module input, not a forked root.

### CON-004 — Data is not code

- A JSON policy in a heredoc is unlintable, hand-escaped, and diffs as one string. Move it to `templates/` and
  keep the interpolation in the `templatefile()` call.
- Template variables are explicit: `templatefile()` fails on an undeclared reference, so the argument map is the
  template's boundary contract.
- Keep `.json.tftpl` valid-JSON-shaped so an editor and `jq`-style tooling still parse the un-interpolated file.

```hcl
# wrong — JSON in a heredoc: unlintable, hand-escaped, diffs as one string
policy = <<-EOT
  {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", ...}]}
EOT

# right — a file the JSON tooling reads, interpolation preserved
policy = templatefile("${path.module}/templates/app_policy.json.tftpl", {
  bucket_arn = aws_s3_bucket.app.arn
})
```

### CON-005 — Typed, validated boundaries

- Every `variable` declares a `type`. Bare `any` is prohibited; if a module genuinely forwards an opaque value,
  the reason goes in `description`.
- Prefer `object({...})` and `map(object({...}))` over `map(string)`, with `optional(<type>, <default>)` for
  attributes that have a safe default.
- Add a `validation` block for every constraint the type cannot express — CIDR shape, allowed region, name
  length, mutually exclusive inputs — with an `error_message` naming the offending value.
- Outputs are the module's public API: `description` on every one, and `sensitive = true` on any output derived
  from a secret. Emit the two attributes a caller needs, not the whole resource object.
- Secrets arrive from a data source or `TF_VAR_` in the environment. Never a literal, never a `default`.

```hcl
# wrong — untyped and unvalidated; the error surfaces inside the provider
variable "subnets" { type = any }

# right — declared shape plus the constraint the type cannot express
variable "subnets" {
  type = map(object({ cidr = string, public = optional(bool, false) }))
  validation {
    condition     = alltrue([for s in var.subnets : can(cidrnetmask(s.cidr))])
    error_message = "Each subnet cidr must be valid IPv4 CIDR notation."
  }
}
```

### CON-006 — Extension by addition

- A new environment, region, or tenant is a new `.tfvars` file or a new key in a `for_each` map — not a new
  `count = var.is_prod ? 1 : 0` branch inside an existing resource.
- Prefer `for_each` over `count` for named sets: `count` addresses by index, so removing the first element
  destroys and recreates every resource after it.
- A module gains a capability as an optional typed input with a safe default, so existing callers are untouched.
- Do not add a variable, feature flag, or `dynamic` block with exactly one caller passing the default.

### CON-007 — Errors travel

- A module refuses to proceed on bad state rather than applying it: `precondition` on the resource whose
  assumption it is, `postcondition` on a data source that must resolve to exactly one object.
- `check` blocks report post-apply health as a warning and do not block an apply — never use one where the
  intent was a `precondition`.
- `ignore_changes` names specific attributes and carries a comment stating what owns the field and what drift is
  therefore invisible. `ignore_changes = all` hides every future diff and is not permitted.
- `prevent_destroy = true` on state backends, data stores, and KMS keys; the blast radius of the alternative is
  unrecoverable.
- `try()` discards the cause. Use it for a genuinely optional attribute, never to paper over a missing input —
  that case is a `validation` block with a message.

```hcl
# wrong — hides every future drift, cause unrecorded
lifecycle { ignore_changes = all }

# right — one field, why it drifts, and what the module refuses to do
lifecycle {
  # desired_count is owned by the autoscaler; Terraform would fight it every apply.
  ignore_changes = [desired_count]
  precondition {
    condition     = var.min_capacity <= var.max_capacity
    error_message = "min_capacity must not exceed max_capacity."
  }
}
```

### CON-008 — Tests first

- Write the `run` block before the code: an `expect_failures = [var.<name>]` run proves a `validation` rejects
  bad input, and it must be observed failing before the validation exists.
- Default to `command = plan` — it asserts behavior without creating anything. Reserve `command = apply` for
  assertions that only a real object can answer.
- Mutate to prove the guard: relax the `validation` condition, confirm exactly that run fails, restore, confirm
  the diff is clean.
- `terraform fmt -check` and `terraform validate` are not tests. They prove style and type wiring; only a plan
  assertion pins behavior.
- Vary the fixture across environments — a suite that only ever loads `dev.tfvars` proves nothing about the
  input shape prod passes.

### CON-009 — Structure is a contract

- The four-file layout **is** the structure contract: `main.tf` (resources and module calls), `variables.tf`,
  `outputs.tf`, `versions.tf` (`required_version`, `required_providers`, backend). A module missing one of these
  is missing a section of its interface, not saving a file.
- Growth adds a topical file (`iam.tf`, `network.tf`), never a fifth responsibility inside `main.tf`.
- `modules/<name>/` repeats the same four-file layout; tests live at `tests/<name>.tftest.hcl` beside the module
  they cover.
- Resource labels do not repeat the type — `resource "aws_s3_bucket" "app"`, not `"app_bucket"` — and a module's
  sole resource of a type is labelled `this`.
- Provider and backend configuration exist only in the root module; a child module that declares either cannot
  be reused by a second caller.
- Every root module declares a remote backend with locking. Local state is not a starting point to migrate away
  from later — the migration is the expensive part.

### CON-010 — Comments earn their place

- `description` on every variable and output is the documented surface; a `#` comment above the block is not a
  substitute, because the description is what tooling and consumers read.
- Comment the *why* on a `lifecycle` rule, an `ignore_changes` entry, a provider-bug workaround, and every
  `depends_on` that exists because the dependency is not implicit.
- Commented-out resource blocks are deleted. A resource leaving the config is handled by `moved` or `removed`,
  which are real declarations, not by commenting it out.

### CON-011 — Dependencies are liabilities

- `versions.tf` bounds `required_version` and every provider with `~>`. A module with no `required_providers`
  block silently inherits whatever the caller resolved.
- Child modules declare provider *constraints* but never provider *configuration*; only the root configures and
  passes them.
- `.terraform.lock.hcl` is committed for every root module, and `terraform providers lock -platform=...` is run
  for each platform CI and developers use, so CI does not resolve a different hash than a laptop.
- Registry modules are pinned with `version`; git sources are pinned with `?ref=<tag-or-commit-sha>`. A bare
  branch ref is an unpinned dependency.
- `trivy config` runs against the module tree; a provider or module is evaluated on release cadence, maintainer,
  and blast radius before adoption.

### CON-012 — Delete before you add

- Deleting a resource block plans a destroy. Say so in the change; if the object must survive, use a `removed`
  block with `destroy = false` instead of deleting silently.
- Rename a resource or module with a `moved` block, kept until every state has applied it, with the removal date
  in an adjacent comment.
- Removing a variable means removing it from every `.tfvars`, every module call, and the module's outputs and
  descriptions in the same change.
- `terraform validate` accepts unused declarations; `tflint`'s `terraform_unused_declarations` rule is what
  catches the orphaned variable, `locals` entry, or data source.

### CON-013 — No arbitrary execution

Terraform has no evaluator, deserializer, or shell of its own, so `C-DANGER`
defines no pattern for it — the omission is deliberate, not an oversight. The
two places arbitrary execution re-enters are worth stating anyway:

- `provisioner "local-exec"`/`"remote-exec"` runs a shell on the operator's
  machine or the target. Treat every interpolated value in the command as
  attacker-controlled, and prefer a real provider resource over a provisioner.
- `external` data sources execute a program every plan. The program is a trust
  boundary; it must not take its arguments from unvalidated variables.

## Definition of done

- [ ] `terraform fmt -recursive -check` and `terraform validate` pass (`terraform_fmt`, `terraform_validate`).
- [ ] `tflint` passes against `.tflint.hcl` with no new `terraform_unused_declarations` finding.
- [ ] `trivy config` reports no new HIGH or CRITICAL misconfiguration (`terraform_trivy`).
- [ ] Every new or changed `variable` has a `type` other than `any`, a `description`, and a `validation` block
      for each constraint the type cannot express.
- [ ] Every new or changed `output` has a `description`; anything secret-derived is `sensitive = true`.
- [ ] No inline payload over 12 lines: it lives under `templates/` or `files/` and loads via
      `templatefile()`/`file()`.
- [ ] `versions.tf` bounds `required_version` and every provider; `.terraform.lock.hcl` is committed in the
      same change.
- [ ] `terraform test` covers the new behavior, including an `expect_failures` run per new `validation`,
      observed failing before the implementation.
- [ ] `terraform plan` against every environment shows only the intended diff, and each destroy or replace is
      named in the change description.
- [ ] Every `.tf` file is under 300 lines and the root module contains only backend, providers, module calls,
      and their wiring.
