# Phase 1 Data Model: New Agent Skills

**Feature**: 002-new-agent-skills | **Date**: 2026-06-01

These skills have no persistent datastore. The "data model" is the set of in-memory /
on-the-wire structures the helper scripts and SKILL.md workflows produce and consume,
plus the YAML config schema that parameterizes them. Structures are described
language-agnostically; shell scripts emit them as line records or JSON.

---

## 1. Dependency Reference (`version-pin`)

A single pinnable item parsed from a recognized file.

| Field | Type | Notes |
|-------|------|-------|
| `file` | path | Source file (relative to repo root in reports). |
| `line_no` | int | 1-based line for reporting. |
| `ecosystem` | enum | `pip` \| `docker` \| `npm` \| `gha` \| ... (from rule set). |
| `name` | string | Dependency / image / action identifier. |
| `current_expr` | string | Raw current version expression (`latest`, `^1.2`, empty, ...). |
| `resolved_version` | string \| null | Specific version from native tool; null if unresolved. |
| `hash` | string \| null | Integrity hash/digest; null when ecosystem has none or unresolved. |
| `state` | enum | `compliant` \| `violation` \| `bypassed` \| `unresolved`. |
| `bypass_reason` | string \| null | Populated when `state == bypassed`. |

**Validation / rules**:
- `violation` ⇔ loose per FR-001 (no specific version, mutable tag, or missing hash where supported).
- `compliant` entries are emitted unchanged (FR-006); a second run reclassifies any prior fix as `compliant` (idempotency, SC-002).
- `unresolved` ⇒ non-fatal warning (FR-007); file untouched for that entry.
- `bypassed` ⇒ inline marker present (R3); line left byte-for-byte unchanged.

**Lifecycle**: `parsed → classified(state) → [on-demand] rewritten | [hook] reported`.

---

## 2. Pinning Rule Set (`version-pin`, config)

Schema for the `version_pin` block in `command_config.yml`. Data, not code (R4).

```yaml
version_pin:
  rules:
    - id: pip-requirements
      match: ["requirements*.txt"]          # glob(s)
      ecosystem: pip
      resolve_cmd: "pip-compile --generate-hashes"  # native tool (R1)
      hash: required                         # required | optional | none
    - id: docker-compose
      match: ["docker-compose.yml", "docker-compose.yaml", "compose.yaml"]
      ecosystem: docker
      resolve_cmd: "docker manifest inspect"
      hash: digest
    # ... Dockerfile, package.json, github-actions
  protected_bypass_marker: "version-pin:ignore"
```

| Field | Type | Notes |
|-------|------|-------|
| `rules[].id` | string | Unique rule key. |
| `rules[].match` | glob[] | File names/patterns the hook + on-demand run apply to. |
| `rules[].ecosystem` | enum | Drives parser + hash form. |
| `rules[].resolve_cmd` | string | Native tool invocation (R1); absence ⇒ warning. |
| `rules[].hash` | enum | `required` \| `optional` \| `digest` \| `none`. |

---

## 3. PR Assessment (`pr-review`)

One record per open PR.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | PR/MR number. |
| `title` | string | |
| `author` | string | |
| `age_days` | int | Days since last activity. |
| `mergeable` | enum | `clean` \| `conflicting` \| `unknown`. |
| `checks` | enum | `passing` \| `failing` \| `pending` \| `none`. |
| `branch_merged` | bool | Head already merged into base. |
| `superseded_by` | string \| null | Another open PR covering the same branch/scope. |
| `draft` | bool | |
| `disposition` | enum | `keep` \| `merge` \| `close` \| `needs-rebase`. |
| `rationale` | string | One-line justification (FR-013). |

**Disposition heuristic** (R5): `branch_merged \|\| superseded_by` → `close`;
`conflicting \|\| checks==failing` → `needs-rebase`; `mergeable==clean && checks==passing && !draft` → `merge`; else `keep`.

**Invariant**: produced read-only; no field mutates a PR (FR-014).

---

## 4. Branch Candidate (`branch-clean`)

One record per local branch (and remote when `--include-remote`).

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Branch short name. |
| `scope` | enum | `local` \| `remote`. |
| `reason` | enum | `merged` \| `gone` \| `stale` \| `none`. |
| `last_activity_days` | int | For `stale` classification. |
| `protected` | bool | Default/release/current-HEAD ⇒ true (FR-017). |
| `is_current` | bool | Checked-out branch. |
| `proposed_action` | enum | `delete-candidate` \| `skip-protected` \| `skip-unmerged`. |
| `delete_result` | enum \| null | `deleted` \| `failed` \| null (dry-run). |

**Rules**:
- `protected \|\| is_current` ⇒ `proposed_action = skip-protected`, never a candidate (FR-017).
- Unmerged branch ⇒ never `reason == merged`; default path never force-deletes (FR-020).
- `delete_result` populated only on `--apply`; failures reported, not swallowed (FR-019).

---

## 5. Docs Run Report (`docs-all`)

| Field | Type | Notes |
|-------|------|-------|
| `order` | string[] | Ordered sub-skill names actually invoked. |
| `precedence_reason` | string | Why this order (changed-file signal or "default fallback"). |
| `results[]` | record[] | Per sub-skill: `{ skill, status: success\|failed\|skipped, summary }`. |

**Rules**: every dispatched sub-skill appears in `results` (FR-010); a `failed` entry does
not abort remaining sub-agents (FR-011); `docs-improve` ordered after the others (R7).

---

## Cross-cutting: Skill Registration (config, all four)

Per skill, two config additions (FR-021/FR-022):

- `command_config.yml → tool_policies.<skill>`: `allowed[]`, `forbidden[]`,
  `parallel_agents`, `validation_tier`, optional `mcp_servers[]`.
- `validation_criteria.yml → command_overrides.<skill>`: `tier1_required`,
  `tier2_required`, `tier2_checks[]`, `parallel_agents` / `_condition`.

Tier assignment (R8): `version-pin` Tier 1; `branch-clean` Tier 1 on `--apply`;
`docs-all` and `pr-review` Tier 2.
