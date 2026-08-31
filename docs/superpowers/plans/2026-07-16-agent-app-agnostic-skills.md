# Agent/App-Agnostic Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Manifest skills capability-driven instead of vendor-coupled: one tracker abstraction (GitHub/GitLab/Linear/Jira), a gap-free forge dispatcher, CI-platform-aware ci-* skills, and a single agent-fleet roster.

**Architecture:** Registry as source of truth (`tracker_providers.yml`), thin dispatchers as accelerators (`tracker_ops.sh` fronting `git_ops.sh`/`linear_ops.sh`), MCP for agent-context-only providers (Jira). Spec: `docs/superpowers/specs/2026-07-16-agent-app-agnostic-skills-design.md`.

**Tech Stack:** Bash (shellcheck-clean), Python 3 + PyYAML (registry resolver), bats-core, pytest, yamllint.

## Global Constraints

- Access precedence per provider: **MCP → CLI → git → API**; raw API only inside ops wrappers, via `gh api`/`glab api` (never curl in a skill).
- Skills reference capabilities/role-named seams, never vendor names (except in config and examples).
- Canonical statuses: `planned`, `in-progress`, `needs-review`, `done` (labels.yml is the label source of truth).
- Shell: `set -euo pipefail`; canonical `err() { ... "<script>: $*" >&2; }`; every user-facing script handles `--help` (≤15 lines, exit 0, **before** any config/dependency lookup).
- Hooks are fail-open: a tracker failure never blocks a commit/PR, but the reason is logged — never a silent green.
- Distinct exit codes from `tracker_ops.sh`: `3` = provider unsupported in shell context (MCP-only), `4` = operation not implemented for provider. Callers treat 3/4 as "skip loudly".
- bats: stub CLIs with recording/exit-127 shim scripts on PATH (never PATH subtraction — breaks on merged-/usr runners). No `bats … | tail` (masks failures).
- After ANY skill add/change: regenerate derived docs (cursor .mdc, COMMANDS/GEMINI/AGENTS guides) and run `pre-commit run --from-ref origin/main --to-ref HEAD` before opening a PR.
- Live verification: all four tracker providers (GitHub, GitLab, Linear, Jira Cloud sandbox via Atlassian MCP). A provider's `verified: true` is set only after its contract-matrix column passes.

---

# PHASE 1 — Tracker abstraction

### Task 1: Registry file `tracker_providers.yml`

**Files:**
- Create: `configs/claude/config/tracker_providers.yml`
- Test: `tests/python/test_tracker_registry.py` (schema portion)

**Interfaces:**
- Produces: YAML with top-level keys `default_provider`, `phase_to_canonical_status`, `providers.{github,gitlab,linear,jira}` each having `access` (ordered list), `status_via`, `status_map`, `tier_map`, `verified`, `missing_tier_behavior`; jira additionally `mcp_tools`. Consumed by Task 2 resolver and Task 9 (lifecycle-run re-point).

- [ ] **Step 1: Write the failing schema test**

```python
# tests/python/test_tracker_registry.py
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "configs/claude/config/tracker_providers.yml"


def load():
    return yaml.safe_load(REG.read_text())


def test_registry_exists_and_parses():
    data = load()
    assert isinstance(data, dict)


def test_all_four_providers_present():
    assert set(load()["providers"]) == {"github", "gitlab", "linear", "jira"}


def test_access_is_ordered_list_from_allowed_methods():
    allowed = {"mcp", "cli", "git", "api"}
    for name, p in load()["providers"].items():
        assert isinstance(p["access"], list) and p["access"], name
        assert set(p["access"]) <= allowed, name


def test_jira_is_mcp_only_and_has_tool_map():
    jira = load()["providers"]["jira"]
    assert jira["access"] == ["mcp"]
    assert "transition" in jira["mcp_tools"]


def test_status_maps_cover_all_canonical_statuses():
    canon = {"planned", "in-progress", "needs-review", "done"}
    for name, p in load()["providers"].items():
        assert set(p["status_map"]) == canon, name


def test_every_provider_declares_verified_flag():
    for name, p in load()["providers"].items():
        assert isinstance(p["verified"], bool), name


def test_default_provider_is_a_known_provider():
    data = load()
    assert data["default_provider"] in data["providers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_tracker_registry.py -v`
Expected: FAIL (`FileNotFoundError` — registry does not exist yet)

- [ ] **Step 3: Create the registry**

Copy `configs/claude/config/lifecycle_providers.yml` content as the base (keep `phase_to_canonical_status` and every provider's `status_via`, `tier_map`, `status_map`, `missing_tier_behavior`, and jira's `mcp_tools` verbatim), then apply these changes:

```yaml
# tracker_providers.yml — issue-tracker provider registry (evolves lifecycle_providers.yml;
# spec: docs/superpowers/specs/2026-07-16-agent-app-agnostic-skills-design.md).
# Access precedence per provider is an ORDERED list: mcp > cli > git > api.
# Agent-context skills use the first available method; hooks/scripts start at cli.

default_provider: github   # used when no override and remote is not github/gitlab

# (phase_to_canonical_status block copied verbatim from lifecycle_providers.yml)

providers:
  github:
    access: [cli, api]      # prepend mcp when a GitHub MCP server is registered
    verified: false          # flipped by the Task 12 contract matrix
    # status_via/tier_map/status_map/missing_tier_behavior copied verbatim
  gitlab:
    access: [cli, api]
    verified: false
    # ...copied verbatim
  linear:
    access: [mcp, cli, api]  # cli = linear_ops.sh GraphQL engine
    verified: false
    # ...copied verbatim (status_via: transition, workflow-state status_map)
  jira:
    access: [mcp]
    verified: false
    # ...copied verbatim including mcp_tools
```

Replace the old per-provider scalar `access: cli` / `access: graphql` / `access: mcp` keys with the ordered lists above (linear's `graphql` becomes the `cli` engine + `api` fallback). Add one comment line under the canonical-operation heading:

```yaml
# Canonical operations (implemented by tracker_ops.sh): issue-list issue-view
# issue-create issue-comment issue-transition issue-label issue-close
# duplicate-mark sub-issue-create sub-issue-list.
# Where a provider lacks a native construct the mapping is documented here:
# duplicate-mark = native state on linear/jira; close + "Duplicate of #N"
# comment + `duplicate` label on github/gitlab.
```

- [ ] **Step 4: Run tests + yamllint to verify pass**

Run: `pytest tests/python/test_tracker_registry.py -v && yamllint configs/claude/config/tracker_providers.yml`
Expected: all PASS, yamllint clean

- [ ] **Step 5: Commit**

```bash
git add configs/claude/config/tracker_providers.yml tests/python/test_tracker_registry.py
git commit -m "feat(tracker): add tracker_providers.yml registry (4 providers, ordered access)"
```

### Task 2: Registry resolver `tracker_registry.py`

**Files:**
- Create: `configs/claude/scripts/tracker_registry.py`
- Test: `tests/python/test_tracker_registry.py` (append resolver tests)

**Interfaces:**
- Produces CLI: `tracker_registry.py status <provider> <canonical>` → prints the provider's label/state name; `tracker_registry.py access <provider>` → prints methods one per line; `tracker_registry.py default-provider` → prints it; `tracker_registry.py mcp-tool <provider> <op>` → prints MCP tool name. Exit 2 on unknown provider/status. Consumed by `tracker_ops.sh` (Task 4) and agent-context skills.

- [ ] **Step 1: Write the failing resolver tests**

Append to `tests/python/test_tracker_registry.py`:

```python
import subprocess, sys

SCRIPT = REPO / "configs/claude/scripts/tracker_registry.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def test_status_lookup_linear_transition_name():
    r = run("status", "linear", "needs-review")
    assert r.returncode == 0 and r.stdout.strip() == "In Review"


def test_status_lookup_github_label():
    r = run("status", "github", "planned")
    assert r.returncode == 0 and r.stdout.strip() == "planned"


def test_access_list_order_preserved():
    r = run("access", "linear")
    assert r.stdout.split() == ["mcp", "cli", "api"]


def test_unknown_provider_exits_2():
    r = run("status", "bitbucket", "planned")
    assert r.returncode == 2 and "bitbucket" in r.stderr


def test_mcp_tool_lookup_jira():
    r = run("mcp-tool", "jira", "transition")
    assert r.stdout.strip() == "transitionJiraIssue"
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/python/test_tracker_registry.py -v` → new tests FAIL (script missing).

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""tracker_registry.py - read-only resolver for tracker_providers.yml.

Usage:
  tracker_registry.py status <provider> <canonical-status>
  tracker_registry.py access <provider>
  tracker_registry.py default-provider
  tracker_registry.py mcp-tool <provider> <operation>
Exit codes: 0 ok, 1 usage, 2 unknown provider/key.
"""

import sys
from pathlib import Path

import yaml

REG = Path(__file__).resolve().parent.parent / "config" / "tracker_providers.yml"


def die(code, msg):
    print(f"tracker-registry: {msg}", file=sys.stderr)
    sys.exit(code)


def main(argv):
    if len(argv) >= 1 and argv[0] in ("--help", "-h"):
        print(__doc__.strip())
        return 0
    if not argv:
        die(1, "missing subcommand (see --help)")
    data = yaml.safe_load(REG.read_text())
    cmd, rest = argv[0], argv[1:]
    if cmd == "default-provider":
        print(data["default_provider"])
        return 0
    if cmd in ("status", "access", "mcp-tool"):
        if not rest:
            die(1, f"{cmd}: missing provider")
        provider = rest[0]
        p = data["providers"].get(provider)
        if p is None:
            die(
                2,
                f"unknown provider: {provider} (known: {', '.join(data['providers'])})",
            )
        if cmd == "access":
            print("\n".join(p["access"]))
            return 0
        if len(rest) < 2:
            die(1, f"{cmd}: missing key")
        key = rest[1]
        table = p["status_map"] if cmd == "status" else p.get("mcp_tools", {})
        if key not in table:
            die(2, f"unknown {cmd} key for {provider}: {key}")
        print(table[key])
        return 0
    die(1, f"unknown subcommand: {cmd}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

`chmod +x configs/claude/scripts/tracker_registry.py`

- [ ] **Step 4: Verify pass** — `pytest tests/python/test_tracker_registry.py -v` → all PASS.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(tracker): add tracker_registry.py resolver CLI"`

### Task 3: Provider detection in `tracker_ops.sh`

**Files:**
- Create: `configs/claude/scripts/tracker_ops.sh` (detection + help + scaffolding only)
- Test: `tests/bats/tracker_ops.bats`

**Interfaces:**
- Produces: `tracker_ops.sh --provider P …` flag, else resolution order `MANIFEST_TRACKER` env → `.manifest-tracker` repo-root marker file → `git_platform.sh` (github/gitlab) → `tracker_registry.py default-provider`. Verb dispatch added in Task 4.

- [ ] **Step 1: Write failing bats tests**

```bash
# tests/bats/tracker_ops.bats
setup() {
    SCRIPT="${BATS_TEST_DIRNAME}/../../configs/claude/scripts/tracker_ops.sh"
    TMPDIR_T="$(mktemp -d)"
    STUBS="${TMPDIR_T}/stubs"; mkdir -p "${STUBS}"
    PATH="${STUBS}:${PATH}"
    export MANIFEST_GIT_PLATFORM=git   # neutralize remote detection by default
}

teardown() { rm -rf "${TMPDIR_T}"; }

@test "help exits 0 before any config lookup" {
    run bash "${SCRIPT}" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "MANIFEST_TRACKER env overrides detection" {
    MANIFEST_TRACKER=linear run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "linear" ]
}

@test "marker file beats remote detection" {
    cd "${TMPDIR_T}" && git init -q .
    echo "jira" > .manifest-tracker
    run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "jira" ]
}

@test "github remote resolves to github" {
    unset MANIFEST_GIT_PLATFORM
    MANIFEST_GIT_PLATFORM=github run bash "${SCRIPT}" resolve-provider
    [ "$output" = "github" ]
}

@test "plain git falls through to registry default" {
    run bash "${SCRIPT}" resolve-provider
    [ "$status" -eq 0 ]
    [ "$output" = "github" ]   # default_provider in registry
}

@test "invalid provider name rejected" {
    MANIFEST_TRACKER=bitbucket run bash "${SCRIPT}" resolve-provider
    [ "$status" -ne 0 ]
    [[ "$output" == *"bitbucket"* ]]
}
```

- [ ] **Step 2: Run to verify fail** — `bats tests/bats/tracker_ops.bats` → all FAIL (script missing).

- [ ] **Step 3: Implement detection scaffold**

```bash
#!/usr/bin/env bash
# tracker_ops.sh - Provider-agnostic issue-tracker operations dispatcher.
# Engines: git_ops.sh (github/gitlab), linear_ops.sh (linear); jira is MCP-only.
# Registry: configs/claude/config/tracker_providers.yml (via tracker_registry.py).

set -euo pipefail

usage() {
    cat << 'USAGE'
Usage: tracker_ops.sh [--provider github|gitlab|linear|jira] <verb> [args...]
Verbs: resolve-provider | issue-list | issue-view N | issue-create |
       issue-comment N TEXT | issue-transition N CANONICAL_STATUS |
       issue-label N --add-label L [--remove-label L] | issue-close N |
       duplicate-mark N --duplicate-of M | sub-issue-create | sub-issue-list N
Detection: --provider > MANIFEST_TRACKER > .manifest-tracker file >
           git remote (github/gitlab) > registry default_provider.
Exit codes: 3 = provider is MCP-only in shell context; 4 = verb not
implemented for provider (both mean: skip loudly, do not fail silently).
USAGE
}
[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && { usage; exit 0; }

err() { if [[ -t 2 ]]; then printf '\033[0;31m%s\033[0m\n' "tracker-ops: $*" >&2; else printf '%s\n' "tracker-ops: $*" >&2; fi; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${SCRIPT_DIR}/tracker_registry.py"
GIT_OPS="${SCRIPT_DIR}/git_ops.sh"
LINEAR_OPS="${SCRIPT_DIR}/linear_ops.sh"

valid_provider() { case "$1" in github | gitlab | linear | jira) return 0 ;; *) return 1 ;; esac; }

resolve_provider() {
    local p=""
    if [[ -n "${FORCED_PROVIDER:-}" ]]; then p="${FORCED_PROVIDER}"
    elif [[ -n "${MANIFEST_TRACKER:-}" ]]; then p="${MANIFEST_TRACKER}"
    else
        local root
        root=$(git rev-parse --show-toplevel 2> /dev/null || true)
        if [[ -n "${root}" && -f "${root}/.manifest-tracker" ]]; then
            p=$(tr -d '[:space:]' < "${root}/.manifest-tracker")
        else
            local plat
            plat=$(bash "${SCRIPT_DIR}/git_platform.sh" 2> /dev/null || echo git)
            case "${plat}" in
                github | gitlab) p="${plat}" ;;
                *) p=$(python3 "${REGISTRY}" default-provider) ;;
            esac
        fi
    fi
    if ! valid_provider "${p}"; then
        err "invalid provider: ${p} (valid: github gitlab linear jira)"
        return 1
    fi
    echo "${p}"
}

FORCED_PROVIDER=""
if [[ "${1:-}" == "--provider" ]]; then
    FORCED_PROVIDER="$2"
    shift 2
fi
[[ $# -eq 0 ]] && { usage >&2; exit 1; }
verb="$1"
shift

provider=$(resolve_provider) || exit 1

case "${verb}" in
    resolve-provider)
        echo "${provider}"
        exit 0
        ;;
    *)
        err "Unknown verb: ${verb}"
        usage >&2
        exit 1
        ;;
esac
```

`chmod +x configs/claude/scripts/tracker_ops.sh`

- [ ] **Step 4: Verify pass** — `bats tests/bats/tracker_ops.bats && shellcheck configs/claude/scripts/tracker_ops.sh` → PASS/clean.

- [ ] **Step 5: Commit** — `git commit -am "feat(tracker): tracker_ops.sh provider detection + help"`

### Task 4: Verb dispatch in `tracker_ops.sh`

**Files:**
- Modify: `configs/claude/scripts/tracker_ops.sh` (replace the verb `case` block)
- Test: `tests/bats/tracker_ops.bats` (append)

**Interfaces:**
- Consumes: `git_ops.sh` verbs (`issue-list/view/create/comment/close/edit`), `linear_ops.sh` verbs (`issue-list/view/comment/close/update`, `transition-state`, `issue-mark-duplicate`, `create-sub-issue`, `list-sub-issues`), `tracker_registry.py status`.
- Produces: the canonical verb set for all shell-reachable providers; exit 3 for jira; exit 4 for provider-verb gaps.

- [ ] **Step 1: Append failing bats tests** (stub `git_ops.sh`/`linear_ops.sh` by pointing `GIT_OPS`/`LINEAR_OPS` env overrides at recording stubs)

First add env-override support expectation to tests:

```bash
make_stub() { # $1=path — records argv to ${1}.calls
    cat > "$1" << 'EOS'
#!/usr/bin/env bash
echo "$@" >> "${0}.calls"
EOS
    chmod +x "$1"
}

@test "issue-list on github delegates to git_ops" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-list --limit 5
    [ "$status" -eq 0 ]
    grep -q "issue-list --limit 5" "${STUBS}/git_ops.sh.calls"
}

@test "issue-close on linear delegates to linear_ops" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-close ENG-42
    [ "$status" -eq 0 ]
    grep -q "issue-close ENG-42" "${STUBS}/linear_ops.sh.calls"
}

@test "issue-transition github swaps canonical labels" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" issue-transition 7 needs-review
    [ "$status" -eq 0 ]
    grep -q -- "--add-label needs-review" "${STUBS}/git_ops.sh.calls"
    grep -q -- "--remove-label planned" "${STUBS}/git_ops.sh.calls"
}

@test "issue-transition linear uses workflow state name" {
    make_stub "${STUBS}/linear_ops.sh"
    LINEAR_OPS_BIN="${STUBS}/linear_ops.sh" MANIFEST_TRACKER=linear \
        run bash "${SCRIPT}" issue-transition ENG-42 needs-review
    grep -q 'transition-state ENG-42 In Review' "${STUBS}/linear_ops.sh.calls"
}

@test "duplicate-mark github closes with comment and label" {
    make_stub "${STUBS}/git_ops.sh"
    GIT_OPS_BIN="${STUBS}/git_ops.sh" MANIFEST_TRACKER=github \
        run bash "${SCRIPT}" duplicate-mark 9 --duplicate-of 4
    grep -q "issue-comment 9 Duplicate of #4" "${STUBS}/git_ops.sh.calls"
    grep -q -- "issue-edit 9 --add-label duplicate" "${STUBS}/git_ops.sh.calls"
    grep -q "issue-close 9" "${STUBS}/git_ops.sh.calls"
}

@test "jira from shell context exits 3 with distinct message" {
    MANIFEST_TRACKER=jira run bash "${SCRIPT}" issue-list
    [ "$status" -eq 3 ]
    [[ "$output" == *"unsupported-in-context"* ]]
}

@test "sub-issue-create on github exits 4 not-implemented" {
    MANIFEST_TRACKER=github run bash "${SCRIPT}" sub-issue-create
    [ "$status" -eq 4 ]
    [[ "$output" == *"not implemented"* ]]
}
```

- [ ] **Step 2: Verify fail** — `bats tests/bats/tracker_ops.bats` → new tests FAIL.

- [ ] **Step 3: Implement dispatch**

Add env-overridable engine paths near the top (replacing the fixed assignments):

```bash
GIT_OPS="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
LINEAR_OPS="${LINEAR_OPS_BIN:-${SCRIPT_DIR}/linear_ops.sh}"
CANONICAL_STATUSES=(planned in-progress needs-review done)
```

Replace the verb `case` block:

```bash
if [[ "${provider}" == "jira" ]]; then
    if [[ "${verb}" == "resolve-provider" ]]; then echo jira; exit 0; fi
    err "unsupported-in-context: jira access is MCP-only; run from agent context"
    err "(registry: tracker_providers.yml providers.jira.access)"
    exit 3
fi

engine() { # route a verb 1:1 to the provider engine
    case "${provider}" in
        github | gitlab) bash "${GIT_OPS}" "$@" ;;
        linear) bash "${LINEAR_OPS}" "$@" ;;
    esac
}

status_name() { python3 "${REGISTRY}" status "${provider}" "$1"; }

case "${verb}" in
    resolve-provider) echo "${provider}" ;;
    issue-list | issue-view | issue-create | issue-comment | issue-close)
        engine "${verb}" "$@"
        ;;
    issue-label)
        case "${provider}" in
            github | gitlab) engine issue-edit "$@" ;;
            linear) engine issue-update "$@" ;;
        esac
        ;;
    issue-transition)
        n="$1" target="$2"
        case "${provider}" in
            github | gitlab)
                args=("${n}")
                for s in "${CANONICAL_STATUSES[@]}"; do
                    [[ "${s}" != "${target}" ]] && args+=(--remove-label "${s}")
                done
                args+=(--add-label "$(status_name "${target}")")
                engine issue-edit "${args[@]}"
                ;;
            linear)
                engine transition-state "${n}" "$(status_name "${target}")"
                ;;
        esac
        ;;
    duplicate-mark)
        n="$1"; shift
        [[ "${1:-}" == "--duplicate-of" ]] || { err "duplicate-mark N --duplicate-of M"; exit 1; }
        primary="$2"
        case "${provider}" in
            linear) engine issue-mark-duplicate "${n}" --duplicate-of "${primary}" ;;
            github | gitlab)
                engine issue-comment "${n}" "Duplicate of #${primary}"
                engine issue-edit "${n}" --add-label duplicate
                engine issue-close "${n}"
                ;;
        esac
        ;;
    sub-issue-create | sub-issue-list)
        case "${provider}" in
            linear)
                [[ "${verb}" == "sub-issue-create" ]] && engine create-sub-issue "$@" || engine list-sub-issues "$@"
                ;;
            github | gitlab)
                err "${verb} not implemented for ${provider} (registry documents the mapping; see spec §4.1)"
                exit 4
                ;;
        esac
        ;;
    *)
        err "Unknown verb: ${verb}"
        usage >&2
        exit 1
        ;;
esac
```

Preconditions to verify while implementing (fix in the engine, not the dispatcher):
- `linear_ops.sh` must have `issue-create` and `issue-update`; if either is missing, add it using the file's existing `graphql_query` helper with the `issueCreate`/`issueUpdate` GraphQL mutations (follow the exact style of the existing `issue-close` implementation — single-quoted mutation, `jq -nc` variables). Add matching cases to `tests/bats/linear_ops.bats`.
- `labels.yml` must contain a `duplicate` label; if missing, add it to the registry (color `#cfd3d7`, description "Duplicate of another issue") so `label-sync` provisions it.

- [ ] **Step 4: Verify pass** — `bats tests/bats/tracker_ops.bats tests/bats/linear_ops.bats && shellcheck configs/claude/scripts/tracker_ops.sh` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(tracker): tracker_ops.sh canonical verb dispatch (github/gitlab/linear; jira exit 3)"`

### Task 5: Migrate `issue-prioritize` off inline platform branching

**Files:**
- Modify: `.retired skill supply/skills/issue-prioritize/SKILL.md`

**Interfaces:**
- Consumes: `tracker_ops.sh resolve-provider`, `tracker_ops.sh issue-list`.

- [ ] **Step 1: Replace detection + fetch sections.** In SKILL.md:
  - Line ~23/31: change flag doc from `--platform github|gitlab|linear` to `--provider github|gitlab|linear|jira (default: auto-detect via tracker_ops.sh)`.
  - Lines ~46-47 script list: replace `git_platform.sh` + `git_ops.sh` entries with `~/.claude/scripts/tracker_ops.sh — provider-agnostic tracker operations (detection + verbs)`.
  - Replace the detection block (lines ~67-92, `PLATFORM=…` + validation `case`) with:

```bash
PROVIDER="${FORCED_PROVIDER:-$(~/.claude/scripts/tracker_ops.sh resolve-provider)}"
echo "Tracker provider: $PROVIDER"
```

  - Replace each per-platform fetch command in the fetch section with `~/.claude/scripts/tracker_ops.sh --provider "$PROVIDER" issue-list …` keeping the per-provider JSON field notes. Keep the Python normalizer, but its `platform` variable is now fed `"$PROVIDER"`, and add a `jira` branch to the normalizer that reads issues fetched via the Atlassian MCP (`searchJiraIssuesUsingJql` — tool name from `tracker_registry.py mcp-tool jira search`) and maps `key→id`, `fields.summary→title`, `fields.labels→labels`, `fields.created→created_at`, `"platform": "jira"`.
  - Add one sentence under Prerequisites: "Jira is agent-context only (MCP); when `PROVIDER=jira`, fetch via the Atlassian MCP tools named in `tracker_providers.yml` instead of `tracker_ops.sh` (which exits 3)."

- [ ] **Step 2: Verify** — `grep -n "git_platform\|case \"\$PLATFORM\"" .retired skill supply/skills/issue-prioritize/SKILL.md` → no hits; `grep -c tracker_ops` → ≥3.

- [ ] **Step 3: Commit** — `git commit -am "refactor(issue-prioritize): route platform work through tracker_ops.sh, add jira"`

### Task 6: Generalize `issue-triage` (Linear-only → provider-agnostic)

**Files:**
- Modify: `.retired skill supply/skills/issue-triage/SKILL.md`
- Create: `configs/claude/config/tracker_triage.yml` (rename+generalize of `linear_triage.yml`)
- Modify: references to `linear_triage.yml` (`grep -rl linear_triage .retired skill supply configs docs`)

**Interfaces:**
- Consumes: `tracker_ops.sh` verbs `issue-list`, `issue-close`, `duplicate-mark`; `tracker_registry.py`.

- [ ] **Step 1: Create `tracker_triage.yml`.** Copy `linear_triage.yml` content; rename any Linear-specific key names to neutral ones (e.g. a `linear:` root or `teams:` key becomes `scopes:`; keep scoring weights, duplicate-detection, and staleness thresholds verbatim); add a header comment: `# tracker_triage.yml — provider-neutral triage scoring (was linear_triage.yml). Provider specifics come from tracker_providers.yml.` Keep `linear_triage.yml` in place for one release with a deprecation comment pointing at the new file (delete in Phase 2 cleanup).

- [ ] **Step 2: Rewrite SKILL.md coupling points:**
  - Frontmatter description: "Comprehensive issue audit for the configured tracker (GitHub, GitLab, Linear, or Jira): …" (drop "Linear").
  - Prereq lines ~39-40, 51: `linear_ops.sh` → `tracker_ops.sh`; `linear_triage.yml` → `tracker_triage.yml`; drop the `~/.config/linear/token` prereq to a per-provider note ("linear: LINEAR_API_KEY or ~/.config/linear/token; github/gitlab: gh/glab auth; jira: Atlassian MCP").
  - Fetch blocks (~lines 127-134): `linear_ops.sh issue-list …` → `tracker_ops.sh issue-list …`; the `team-list` loop stays but becomes conditional: "when `PROVIDER=linear`, iterate teams via `linear_ops.sh team-list` (engine-level, linear-only concept); other providers list by label/milestone instead".
  - Action blocks (~lines 609, 629): `linear_ops.sh issue-mark-duplicate A --duplicate-of B` → `tracker_ops.sh duplicate-mark A --duplicate-of B`; `linear_ops.sh issue-close` → `tracker_ops.sh issue-close`.
  - Precondition checks (~lines 688-693): check `tracker_ops.sh` executable + `tracker_triage.yml` exists instead of the Linear pair.

- [ ] **Step 3: Verify** — `bats tests/bats/tracker_ops.bats` still green; `grep -n "linear_ops\|linear_triage" .retired skill supply/skills/issue-triage/SKILL.md` → only inside the provider-specific linear note; `yamllint configs/claude/config/tracker_triage.yml` clean.

- [ ] **Step 4: Commit** — `git commit -am "refactor(issue-triage): provider-agnostic via tracker_ops + tracker_triage.yml"`

### Task 7: Re-point hook library `issue_support.sh`

**Files:**
- Modify: `configs/claude/scripts/issue_support.sh`
- Test: `tests/bats/issue_support.bats` (existing — extend)

**Interfaces:**
- Consumes: `tracker_ops.sh issue-transition/issue-comment/issue-view/resolve-provider` (env-overridable `TRACKER_OPS_BIN` for tests).
- Produces: unchanged public functions (`process_issue`, `transition_issue`, `comment_backlink`, …) so `issue-sync-commit`/`issue-sync-pr` skills need no change beyond docs.

- [ ] **Step 1: Extend `tests/bats/issue_support.bats`** with cases asserting (a) `transition_issue` shells out to a stubbed `tracker_ops.sh` with `issue-transition N <target>`, (b) a stub exiting 3 (jira-style) makes the function return 0 (fail-open) while logging `unsupported-in-context`, (c) existing github/gitlab tests still pass unchanged. Use the same `make_stub` recording-stub pattern as `tracker_ops.bats`.

- [ ] **Step 2: Verify new tests fail.**

- [ ] **Step 3: Implement.** Add near the top of `issue_support.sh`:

```bash
TRACKER_OPS_BIN="${TRACKER_OPS_BIN:-${SCRIPT_DIR}/tracker_ops.sh}"
```

Rewrite the internals of `transition_issue` (line ~204) and `comment_backlink` (line ~227) to call `"${TRACKER_OPS_BIN}" issue-transition …` / `issue-comment …` instead of their inline `if [[ "${platform}" == "github" ]]` branches, wrapping each call in the file's existing fail-open pattern plus:

```bash
rc=0
"${TRACKER_OPS_BIN}" issue-transition "${n}" "${target}" || rc=$?
if [[ ${rc} -eq 3 || ${rc} -eq 4 ]]; then
    err "tracker provider limitation (rc=${rc}) — skipping sync, not failing hook"
    return 0
fi
```

Keep `issue_record`/`ensure_closing_keyword` (PR-side, forge-specific) on `git_ops.sh` — they move in Phase 2. `detect_platform` (line ~311) now calls `"${TRACKER_OPS_BIN}" resolve-provider`.

- [ ] **Step 4: Verify** — `bats tests/bats/issue_support.bats tests/bats/issue_support_hook.bats` → PASS; `shellcheck configs/claude/scripts/issue_support.sh` clean.

- [ ] **Step 5: Commit** — `git commit -am "refactor(issue-sync): issue_support.sh transitions/comments via tracker_ops (fail-open on rc 3/4)"`

### Task 8: Migrate `issue-dev-auto` + `issue-prep-auto` direct `gh` calls

**Files:**
- Modify: `.retired skill supply/skills/issue-dev-auto/SKILL.md`, `.retired skill supply/skills/issue-prep-auto/SKILL.md`

- [ ] **Step 1: Locate** — `grep -n '\bgh \|git_ops' .retired skill supply/skills/issue-dev-auto/SKILL.md .retired skill supply/skills/issue-prep-auto/SKILL.md`.
- [ ] **Step 2: Replace** every issue-scoped call: `gh issue list/view/edit/comment …` and `git_ops.sh issue-*` label mutations become `tracker_ops.sh issue-list/issue-view/issue-label/issue-comment`; status-label swaps (`--remove-label in-progress --add-label needs-review` style sequences) become single `tracker_ops.sh issue-transition N <canonical>` calls. PR-scoped calls (`gh pr create`, `pr-view`) stay on `git_ops.sh` (Phase 2 domain). The `auto-dev` opt-in label check becomes `tracker_ops.sh issue-list --label auto-dev` (github/gitlab pass-through; linear uses its label filter).
- [ ] **Step 3: Verify** — `grep -n '\bgh issue' <both SKILL.md>` → no hits.
- [ ] **Step 4: Commit** — `git commit -am "refactor(issue-dev-auto,issue-prep-auto): issue ops via tracker_ops"`

### Task 9: Re-point `lifecycle-run` and retire `lifecycle_providers.yml`

**Files:**
- Modify: every referrer — `grep -rln lifecycle_providers .retired skill supply configs docs tests`
- Delete: `configs/claude/config/lifecycle_providers.yml`
- Test: `tests/bats/lifecycle.bats` (existing)

- [ ] **Step 1:** Replace each `lifecycle_providers.yml` path reference with `tracker_providers.yml`. Behavior is unchanged: Task 1 copied all lifecycle keys verbatim (`phase_to_canonical_status`, `tier_map`, `status_via`, `missing_tier_behavior`, `mcp_tools`).
- [ ] **Step 2:** Delete `configs/claude/config/lifecycle_providers.yml`.
- [ ] **Step 3: Verify** — `bats tests/bats/lifecycle.bats` PASS; `grep -rn lifecycle_providers . --exclude-dir=.git` → only historical spec/plan docs.
- [ ] **Step 4: Commit** — `git commit -am "refactor(lifecycle): absorb lifecycle_providers.yml into tracker_providers.yml"`

### Task 10: Partial migrations — `repo-clean` + `pr-review` issue portions

**Files:**
- Modify: `.retired skill supply/skills/repo-clean/SKILL.md`, `.retired skill supply/skills/pr-review/SKILL.md`

- [ ] **Step 1:** In both SKILL.md files, replace issue-scoped `git_ops.sh issue-*` / direct `gh issue` calls with `tracker_ops.sh` equivalents (`grep -n 'issue' <file>` to enumerate). Leave every `pr-*` call untouched (Phase 2). In `repo-clean`, leave the raw `gh pr close`/`glab mr close` fallback in place with a comment `# TODO(phase-2): git_ops pr-close` — this is the one sanctioned deferred marker, resolved by Task 13.
- [ ] **Step 2: Verify** — skill text has no vendor-named *issue* commands; `bats tests/bats/pr_review.bats` PASS.
- [ ] **Step 3: Commit** — `git commit -am "refactor(repo-clean,pr-review): issue portions via tracker_ops"`

### Task 11: Docs, config wiring, derived-doc regeneration

**Files:**
- Modify: `CLAUDE.md` (Key Files table: add `tracker_providers.yml`, `tracker_ops.sh`, `tracker_registry.py`, `tracker_triage.yml`; update `linear_triage.yml` row), `docs/COMMANDS.md`, `configs/claude/config/command_config.yml` (tool_policies entries for renamed behavior stay keyed by skill name — verify no orphan keys), CI yamllint file list if explicit.

- [ ] **Step 1:** Apply doc edits; run the derived-docs chain (cursor rules generator + guides) and `pre-commit run --from-ref origin/main --to-ref HEAD`; fix anything it flags (stage fixes before re-running — pre-commit stashes unstaged changes).
- [ ] **Step 2: Verify** — `bats tests/bats/context_budget.bats tests/bats/commands_doc_drift.bats` PASS (deployed-size budget included).
- [ ] **Step 3: Commit** — `git commit -am "docs(tracker): wire tracker abstraction into guides + derived docs"`

### Task 12: Live contract matrix (all four providers)

**Files:**
- Create: `docs/superpowers/specs/2026-07-16-tracker-contract-matrix.md` (results record)
- Modify: `configs/claude/config/tracker_providers.yml` (`verified:` flips)

- [ ] **Step 1:** For each provider × canonical operation, run the real thing against a scratch issue: GitHub (this repo or a scratch repo), GitLab (scratch project), Linear (scratch team, `LINEAR_API_KEY`), Jira (Cloud sandbox via Atlassian MCP tools from agent context, using `tracker_registry.py mcp-tool jira <op>` names). Record each cell PASS/FAIL/N-A (N/A only for documented gaps: `sub-issue-*` on github/gitlab = exit 4; all jira rows exercised via MCP, with the shell path asserted to exit 3).
- [ ] **Step 2:** Fix any failing cell before proceeding (the matrix is the acceptance gate).
- [ ] **Step 3:** Flip `verified: true` for each fully-passing provider; commit matrix + registry: `git commit -am "test(tracker): live 4-provider contract matrix; mark providers verified"`.

---

# PHASE 2 — Forge/PR operations

### Task 13: `git_ops.sh` new verbs — `pr-close`, `pr-comment`, `pr-comments`

**Files:**
- Modify: `configs/claude/scripts/git_ops.sh` (both platform case blocks + usage)
- Test: `tests/bats/git_ops.bats` (append)

**Interfaces:**
- Produces: `pr-close N`, `pr-comment N TEXT`, `pr-comments N` (JSON list of review comments: id, author, path, line, body).

- [ ] **Step 1:** Append bats tests (existing file's stub pattern) asserting: github routes `pr-close`→`gh pr close`, `pr-comment`→`gh pr comment`, `pr-comments`→`gh api repos/{owner}/{repo}/pulls/N/comments`; gitlab routes →`glab mr close`, →`glab mr note`, →`glab api projects/:id/merge_requests/N/notes`.
- [ ] **Step 2:** Verify fail.
- [ ] **Step 3:** Implement in both case blocks, github:

```bash
pr-close)
    gh pr close "$@"
    ;;
pr-comment)
    issue_comment_args --body "$@"
    gh pr comment "${ISSUE_COMMENT_ARGS[@]+"${ISSUE_COMMENT_ARGS[@]}"}"
    ;;
pr-comments)
    pr_num="$1"; shift
    gh api "repos/{owner}/{repo}/pulls/${pr_num}/comments" \
        --jq '[.[] | {id, author: .user.login, path, line, body}]' "$@"
    ;;
```

gitlab:

```bash
pr-close)
    glab mr close "$@"
    ;;
pr-comment)
    issue_comment_args --message "$@"
    glab mr note "${ISSUE_COMMENT_ARGS[@]+"${ISSUE_COMMENT_ARGS[@]}"}"
    ;;
pr-comments)
    mr_num="$1"; shift
    glab api "projects/:id/merge_requests/${mr_num}/notes?sort=asc" \
        --jq '[.[] | select(.system == false) | {id, author: .author.username, path: (.position.new_path // null), line: (.position.new_line // null), body}]' "$@"
    ;;
```

Add all three to both usage texts.
- [ ] **Step 4:** `bats tests/bats/git_ops.bats && shellcheck configs/claude/scripts/git_ops.sh` PASS. Remove the `# TODO(phase-2)` fallback in `repo-clean` (Task 10) → `git_ops.sh pr-close`.
- [ ] **Step 5:** `git commit -am "feat(git-ops): pr-close, pr-comment, pr-comments verbs (gh+glab)"`

### Task 14: Migrate `pr-address-comments` onto git_ops verbs

**Files:**
- Modify: `.retired skill supply/skills/pr-address-comments/SKILL.md`

- [ ] **Step 1:** Replace each `gh api …/pulls/…/comments` fetch with `git_ops.sh pr-comments N`; top-level replies with `git_ops.sh pr-comment N "…"`. Thread-resolution (`gh api graphql resolveReviewThread`) has no glab equivalent — keep it inside a provider-conditional block labeled "github-only: thread resolution" with the gitlab branch posting a `Resolved: <summary>` note instead. Bot names (Copilot/CodeRabbit) stay — they're review *sources* being triaged, not couplings (Task 17 gives them a registry).
- [ ] **Step 2:** Verify — `grep -n 'gh api' SKILL.md` → only inside the labeled github-only block.
- [ ] **Step 3:** `git commit -am "refactor(pr-address-comments): forge-agnostic via git_ops pr-comment verbs"`

### Task 15: Migrate the raw-`gh` PR cluster

**Files:**
- Modify: `.retired skill supply/skills/pr-clean-base/SKILL.md`, `.retired skill supply/skills/pr-reset-reapply/SKILL.md`, `.retired skill supply/skills/pr-merge-stacked/SKILL.md`, `.retired skill supply/skills/merge-stacked-pr-chain/SKILL.md`, `.retired skill supply/skills/premise-verify/SKILL.md`, `.retired skill supply/skills/api-optimize-bulk/SKILL.md`, `configs/claude/scripts/pr_merge_loop.sh`

- [ ] **Step 1:** Per file, `grep -n '\bgh \b'` and classify each call: (a) has a git_ops verb → replace with the verb (`pr-view`, `pr-list`, `pr-diff`, `pr-checks`, `pr-merge`, `pr-edit`, `pr-close`); (b) pure-git equivalent exists (branch reads, merge-base, cherry-pick plumbing) → replace with git (precedence: git > api); (c) genuinely API-only (e.g. retarget base via API, workflow-run queries) → keep, but move into `git_ops.sh` as a named verb with a glab twin where GitLab has the endpoint, or wrap in an explicit provider-conditional "github-only" block where it doesn't.
- [ ] **Step 2:** Verify — `bats tests/bats/pr_merge_loop.bats tests/bats/git_ops.bats` PASS; remaining `gh api` occurrences exist only inside git_ops.sh or labeled github-only blocks.
- [ ] **Step 3:** `git commit -am "refactor(pr-*): route PR cluster through git_ops verbs / git plumbing"`

### Task 16: Stacked-PR GitLab parity check

**Files:**
- Modify: `.retired skill supply/skills/pr-merge-stacked/SKILL.md`, `.retired skill supply/skills/merge-stacked-pr-chain/SKILL.md`

- [ ] **Step 1:** Both skills currently have a single token `glab` mention. After Task 15, walk each documented sequence against a scratch GitLab MR chain (retarget child MR = `glab mr update N --target-branch`), and document any true gap as a labeled gitlab-specific step.
- [ ] **Step 2:** `git commit -am "docs(pr-stacked): verified gitlab parity for stacked-MR flows"`

### Task 17: Review-bot registry

**Files:**
- Create: `configs/claude/config/review_bots.yml`
- Modify: `.retired skill supply/skills/pr-monitor/SKILL.md`, `.retired skill supply/skills/pr-monitor/references/platform-commands.md`, `.retired skill supply/skills/pr-triage-bots/SKILL.md`
- Test: extend `tests/python/` with a schema test mirroring Task 1's pattern

- [ ] **Step 1:** Create the registry:

```yaml
# review_bots.yml — machine reviewers/authors skills may monitor or triage.
# Skills iterate this list; adding a bot is a config change, not a skill edit.
bots:
  copilot:
    author_login: "copilot-pull-request-reviewer[bot]"
    role: reviewer
    invoke: automatic          # reviews PRs without being summoned
  jules:
    author_login: "google-labs-jules[bot]"
    role: reviewer
    invoke: mention            # summoned via mention
    mention: "@google-labs-jules"
  palette:
    author_login: "palette[bot]"
    role: author
  bolt:
    author_login: "bolt[bot]"
    role: author
```

(Verify each `author_login` against real PR history — `git_ops.sh pr-list` + recent bot PRs — before committing; #580/#581 commits name Palette/Bolt.)
- [ ] **Step 2:** Rewrite `pr-monitor`/`pr-triage-bots` bot enumerations to "for each bot in `review_bots.yml` with role=reviewer/author …", keeping per-bot behavioral notes keyed by registry name.
- [ ] **Step 3:** Schema test (all bots have `author_login` + `role`), yamllint, regen derived docs, commit: `git commit -am "feat(bots): review_bots.yml registry; pr-monitor/pr-triage-bots read it"`

### Task 18: GitHub/GitLab MCP decision gate

**Files:**
- Modify (if adopted): `configs/claude/config/mcp_servers.yml`, `configs/claude/config/tracker_providers.yml` (`access:` prepend `mcp`)

- [ ] **Step 1:** Evaluate the official GitHub MCP server and a GitLab MCP server against the verb set skills actually use (Task 13-15 inventory). Adopt only if a server covers ≥ the git_ops verb set with OAuth-capable auth; otherwise record "evaluated, deferred — CLI remains first" in the spec's §5 and stop.
- [ ] **Step 2:** If adopted: register in `mcp_servers.yml`, prepend `mcp` to the provider's `access:` list, re-run the Task 12 matrix rows for agent-context ops, commit.

---

# PHASE 3 — CI platform abstraction

### Task 19: CI platform detection `ci_platform.sh`

**Files:**
- Create: `configs/claude/scripts/ci_platform.sh`
- Test: `tests/bats/ci_platform.bats`

**Interfaces:**
- Produces: prints `github-actions` | `gitlab-ci` | `none`; override `MANIFEST_CI_PLATFORM`. Detection: `.github/workflows/*.yml|yaml` present → github-actions; `.gitlab-ci.yml` present → gitlab-ci; both → prefer the one matching `git_platform.sh`; neither → none.

- [ ] **Step 1:** bats tests for all five cases (github-only, gitlab-only, both+github remote, both+gitlab remote, neither) using temp git dirs — mirror `git_platform.bats` structure.
- [ ] **Step 2:** Verify fail. **Step 3:** Implement (≈40 lines, same header/err/--help conventions as `git_platform.sh`). **Step 4:** bats + shellcheck PASS. **Step 5:** `git commit -am "feat(ci): ci_platform.sh detection"`

### Task 20: Cross-platform trigger-semantics reference

**Files:**
- Create: `.retired skill supply/skills/ci-audit-triggers/references/gitlab-ci-triggers.md`
- Modify: `.retired skill supply/skills/ci-audit-triggers/SKILL.md`, `.retired skill supply/skills/ci-harden-workflow/SKILL.md`

- [ ] **Step 1:** Write the GitLab reference: the attacker-influence table mapping GitHub concepts to GitLab equivalents — `pull_request_target` ↔ pipelines for merge requests from forks (incl. "pipelines for merged results" + `CI_MERGE_REQUEST_*` variable injection), `issue_comment` triggers ↔ (no native equivalent; webhook-driven), `${{ }}` template injection ↔ `$[[ inputs.* ]]` / `rules:` variable expansion, `author_association` gates ↔ project-membership checks, fork `head.ref` checkout ↔ `CI_MERGE_REQUEST_SOURCE_BRANCH_NAME` usage, secrets exposure ↔ protected variables + protected branches.
- [ ] **Step 2:** Both SKILL.md files gain step 0: "run `ci_platform.sh`; load the matching reference (`github-actions` semantics are the existing body; `gitlab-ci` → references/gitlab-ci-triggers.md); `none` → report and stop." Audit method (source→sink, trigger inventory) stays shared.
- [ ] **Step 3:** Regen derived docs; `git commit -am "feat(ci-audit): gitlab-ci trigger semantics + platform detection step"`

### Task 21: CI failure-reproduction skills — GitLab paths

**Files:**
- Modify: `.retired skill supply/skills/ci-reproduce-failure/SKILL.md`, `.retired skill supply/skills/reproduce-gated-ci-failure-locally/SKILL.md`, `.retired skill supply/skills/ci-diagnose-drift/SKILL.md`

- [ ] **Step 1:** For each `gh run view` / `gh api …/actions/…` sequence, add the gitlab branch: `glab ci list --status failed`, `glab ci get --pipeline-id N`, `glab ci trace <job-id>`; job-definition lookup reads `.gitlab-ci.yml` (+ `include:` resolution) instead of `.github/workflows/*.yml`. `ci-diagnose-drift`'s "where does CI override the repo's linter config" checklist gains the GitLab items: `variables:` blocks, `before_script`, and instance/group-level CI templates.
- [ ] **Step 2:** Structure each skill as: detect via `ci_platform.sh` → shared diagnosis method → per-platform command appendix.
- [ ] **Step 3:** `git commit -am "feat(ci-repro): gitlab-ci reproduction paths"`

### Task 22: `ci-setup` gap pass + Phase 3 live verification

- [ ] **Step 1:** `ci-setup` already templates both platforms — verify its detection now uses `ci_platform.sh` (replace any inline detection) and its GitLab template still matches current glab/GitLab syntax.
- [ ] **Step 2:** Live verification: run `ci-audit-triggers` and `ci-reproduce-failure` against a real GitLab project with a failing pipeline; record results in the contract-matrix doc (new "CI" section). Fix before commit.
- [ ] **Step 3:** `git commit -am "test(ci): live gitlab verification of ci-* platform abstraction"`

---

# PHASE 4 — Agent fleet registry

### Task 23: Single roster `agent_roster.yml`

**Files:**
- Create: `configs/claude/config/agent_roster.yml`
- Test: `tests/python/test_agent_roster.py`

**Interfaces:**
- Produces: per-agent entries `{name, binary, home_dir, prompt_args, model_args, auth_check, enabled_default}` for claude/gemini/cursor/codex/antigravity. This is the single enumeration; consumers in Tasks 24-26.

- [ ] **Step 1:** Schema test (five agents present; every entry has all six keys; `home_dir` starts with `~/.`). **Step 2:** fail. **Step 3:** Create the file by extracting current truth from `configs/claude/config/parallel_agent.yml` (`cli_agents` table: binary/base_args/model_args/prompt_args) and `bootstrap/lib/config.sh` `write_services_config()` defaults; `auth_check` values from `env-check` SKILL.md (`claude auth status`, `gemini auth status`, `cursor-agent --version`, `codex login status`, `agy --version`). **Step 4:** pytest + yamllint PASS. **Step 5:** commit.

- [ ] **Note:** `parallel_agent.yml` keeps its tuning tables (model_tiers, rate limits, credit_fallback) but its `cli_agents` binary/args block now must match the roster — add a pytest asserting the two files agree on `binary` per agent (drift guard) rather than removing the block in one step.

### Task 24: `agents/` package reads the roster

**Files:**
- Modify: `configs/claude/scripts/agents/config.py` (default roster from `agent_roster.yml` instead of `_default_config` literals), `configs/claude/scripts/agents/runners.py`
- Test: `tests/python/` existing agent tests + new `test_runner_generic.py`

- [ ] **Step 1:** Add a failing test: constructing the runner set from a roster containing a *sixth* synthetic CLI-only agent (temp YAML) yields a working generic runner (correct binary/args assembled) with no new subclass.
- [ ] **Step 2:** Refactor `runners.py`: keep SDK-backed special cases (Claude/Gemini `select_backend` logic) but make the CLI path one `GenericCLIAgent` parameterized by roster entry; existing concrete subclasses become roster-driven instantiations (public behavior and `services.yml` gating unchanged).
- [ ] **Step 3:** Full `pytest tests/python/` PASS; run `parallel_agent.py --json "ping"` live to confirm no regression. **Step 4:** commit.

### Task 25: Fleet-inspection skills read the roster

**Files:**
- Modify: `.retired skill supply/skills/env-check/SKILL.md`, `.retired skill supply/skills/config-audit/SKILL.md`, `.retired skill supply/skills/deploy-reconcile/SKILL.md`, `.retired skill supply/skills/deploy-retire-component/SKILL.md`

- [ ] **Step 1:** Replace each hardcoded agent list ("check claude, gemini, cursor, codex, antigravity…") with "iterate `agent_roster.yml` entries: run each `auth_check`, verify each `home_dir` symlink set". Per-agent quirk notes stay, keyed by roster name. `~/.claude/` as the physical config home stays (documented soft assumption per spec §5).
- [ ] **Step 2:** Regen derived docs; commit.

### Task 26: Role-named LLM seams for `skill-evolve` + `graphify`

**Files:**
- Modify: `.retired skill supply/skills/skill-evolve/SKILL.md` (+ `configs/claude/scripts/skillclaw_promote.sh` if it invokes `claude -p` directly), `.retired skill supply/skills/graphify/SKILL.md`
- Test: `tests/bats/skillclaw_promote.bats` (existing — extend)

- [ ] **Step 1:** Introduce `EVOLVE_CLI="${EVOLVE_CLI:-claude}"` and `GRAPHIFY_LLM_CLI="${GRAPHIFY_LLM_CLI:-claude}"` seams (llm-invoke-stdin pattern: role-named, vendor only as default). Every `claude -p` invocation becomes `"${EVOLVE_CLI}" -p` (or the graphify CLI's equivalent backend flag if it exposes one — check `graphify --help`; if the backend is baked into the graphify CLI itself, document the limitation in SKILL.md instead of faking a seam). skill-evolve's *transcript* dependency (`~/.claude/projects` JSONL) is inherent to its data source — document as claude-specific by design, not a defect.
- [ ] **Step 2:** bats: stub `EVOLVE_CLI` and assert the stub is invoked. **Step 3:** commit.

### Task 27: Final sweep + program close-out

- [ ] **Step 1:** Repo-wide audit re-run: `grep -rn 'linear_ops\|gh api\|glab api\|claude -p' .retired skill supply/skills --include=SKILL.md` — every remaining hit must be inside a labeled provider-conditional block, an engine script, or a documented-inherent case (pass-cli, skill-evolve transcripts). Fix strays.
- [ ] **Step 2:** Full regression: `bats tests/bats/ && pytest tests/python/ && shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh && yamllint configs/claude/config/*.yml`, plus `pre-commit run --from-ref origin/main --to-ref HEAD`.
- [ ] **Step 3:** Update the spec's §5 open items with outcomes; regenerate derived docs; final commit.

---

## Self-review notes (spec → plan coverage)

- Spec §4.1 registry (access lists, status/tier maps, detection, verified flags) → Tasks 1-3. §4.2 dispatcher (verbs, exit 3, conventions) → Tasks 3-4. §4.3 migrations: issue-triage→T6, issue-prioritize→T5, issue-sync-*→T7, issue-dev/prep-auto→T8, lifecycle-run→T9, repo-clean/pr-review partial→T10. §4.4 testing (matrix, bats stubs, yamllint, GitHub-first regression) → Tasks 1-4 tests + T12. §4.5 error handling → T4 (exit codes), T7 (fail-open). §3 Phase 2 → T13-18, Phase 3 → T19-22, Phase 4 → T23-26. §5 open items → T18 (MCP gate), T17 (bots), T25 (config home documented), T26 note + T27 close-out.
- Known intentional deferral: `sub-issue-create/list` on github/gitlab returns exit 4 (documented mapping only) — YAGNI until a consumer needs it; lifecycle-run's tier machinery is registry-driven and unaffected.
