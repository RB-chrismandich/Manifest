# Autonomous Issue Developer (`/auto-issue-dev`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a curated, fully autonomous loop that picks an opted-in (`auto-dev`) issue, develops it test-first, and opens a PR for human review — repeating until the eligible queue is empty.

**Architecture:** A small, deterministic, bats-tested shell helper (`auto_issue_dev.sh`) handles issue selection, dependency checking, and failure/dependency flagging by wrapping the existing `git_ops.sh`. A markdown skill (`auto-issue-dev`) develops **one** issue per invocation; the existing `/loop` skill re-runs it with fresh context per issue. Status sync (`planned→in-progress→needs-review`) and the `Closes #N` keyword are delegated to the already-shipped #345 issue-linking hooks.

**Tech Stack:** Bash (set -euo pipefail), Python 3 heredocs for JSON/YAML parsing, `bats` tests with `git_ops.sh` stubs, `gh`/`glab` via `git_ops.sh`, markdown skill + Cursor `.mdc` rule.

**Spec:** `docs/superpowers/specs/2026-06-14-auto-issue-dev-design.md`

**Decision (carried from spec, override if desired):** dependency-blocked issues get the `blocked-dependency` label *alone* (not stacked with `needs-human`). `needs-human` is reserved for dev failures.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `configs/claude/config/labels.yml` | Add `auto-dev`, `needs-human`, `blocked-dependency` labels | Modify |
| `configs/claude/scripts/auto_issue_dev.sh` | Selection + dependency + flagging engine | Create |
| `tests/bats/auto_issue_dev.bats` | Engine tests (mocked `git_ops.sh`) | Create |
| `.skillshare/skills/auto-issue-dev/SKILL.md` | Per-invocation dev procedure | Create |
| `.skillshare/skills/auto-issue-dev/evals/evals.json` | Triggering evals | Create |
| `configs/claude/config/command_config.yml` | `tool_policies.auto-issue-dev` | Modify |
| `configs/cursor/rules/auto-issue-dev.mdc` | Cross-tool parity (generated) | Create (generated) |
| `docs/COMMANDS.md` | Command reference entry | Modify |

Helper interface (locked here; reused verbatim in later tasks):

```
auto_issue_dev.sh <subcommand>
  next-issue [--json]          # first READY auto-dev issue; exit 3 when none
  check-deps <N> [--json]      # exit 2 if unmet deps; 0 if all met
  mark-blocked <N> <reason>    # add needs-human + deduped comment; exit 0 always
  mark-dependency <N> <refs>   # add blocked-dependency + deduped comment; exit 0 always
  --help
```

Env seams (defaults): `GIT_OPS_BIN`, `GIT_PLATFORM_BIN`, `AUTO_ISSUE_DEV_LABEL=auto-dev`, `AUTO_ISSUE_DEV_DEP_LABEL=blocked-dependency`, `AUTO_ISSUE_DEV_FAIL_LABEL=needs-human`.

---

## Task 1: Canonical labels

**Files:**
- Modify: `configs/claude/config/labels.yml`

- [ ] **Step 1: Add the three labels**

In `configs/claude/config/labels.yml`, after the `future` label block (before the `deprecated:` key), add:

```yaml
  - name: auto-dev
    color: "5319E7"
    description: "Eligible for the autonomous issue developer (/auto-issue-dev)"
    platforms: [github, gitlab, linear]

  - name: needs-human
    color: "B60205"
    description: "Auto-dev could not complete; needs a human"
    platforms: [github, gitlab, linear]

  - name: blocked-dependency
    color: "D93F0B"
    description: "Has an unmet dependency; excluded from the auto-dev loop until the blocker merges"
    platforms: [github, gitlab, linear]
```

- [ ] **Step 2: Validate the registry**

Run:
```bash
yamllint configs/claude/config/labels.yml
python3 -c "
import yaml
d=yaml.safe_load(open('configs/claude/config/labels.yml')); labels=d['labels']
names=[l['name'] for l in labels]
for l in labels:
    assert {'name','color','description','platforms'} <= set(l), l
    assert len(l['color'])==6, l
assert len(names)==len(set(names)), 'dup'
assert {'auto-dev','needs-human','blocked-dependency'} <= set(names)
print(f'{len(labels)} labels OK')
"
```
Expected: `yamllint` exits 0; prints `9 labels OK`.

- [ ] **Step 3: Commit**

```bash
git add configs/claude/config/labels.yml
git commit -m "feat(labels): add auto-dev, needs-human, blocked-dependency"
```

---

## Task 2: `auto_issue_dev.sh` skeleton (`--help` + dispatch)

**Files:**
- Create: `configs/claude/scripts/auto_issue_dev.sh`
- Test: `tests/bats/auto_issue_dev.bats`

- [ ] **Step 1: Write the failing test**

Create `tests/bats/auto_issue_dev.bats`:

```bash
#!/usr/bin/env bats
# Tests for configs/claude/scripts/auto_issue_dev.sh

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/auto_issue_dev.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/auto_issue_dev.XXXXXX")
    export FIXTURE_DIR="$TMP/fixtures"; mkdir -p "$FIXTURE_DIR"

    # Stub git_ops.sh: emit fixtures, log calls, honor *_RC
    cat >"$TMP/git_ops.sh" <<'EOF'
#!/usr/bin/env bash
sub="$1"; shift
echo "$sub $*" >> "${CALL_LOG:-/dev/null}"
case "$sub" in
  issue-view)  n="$1"; [[ -f "${FIXTURE_DIR}/issue-${n}.json" ]] && cat "${FIXTURE_DIR}/issue-${n}.json" || true ;;
  pr-view)     n="$1"; [[ -f "${FIXTURE_DIR}/pr-${n}.json" ]] && cat "${FIXTURE_DIR}/pr-${n}.json" || true ;;
  issue-list)  printf '%s' "${ISSUE_LIST_OUT:-[]}" ;;
  issue-edit)    exit "${EDIT_RC:-0}" ;;
  issue-comment) exit "${COMMENT_RC:-0}" ;;
  *) exit "${GITOPS_RC:-0}" ;;
esac
EOF
    chmod +x "$TMP/git_ops.sh"
    cat >"$TMP/git_platform.sh" <<'EOF'
#!/usr/bin/env bash
echo "${STUB_PLATFORM:-github}"
EOF
    chmod +x "$TMP/git_platform.sh"
    export GIT_OPS_BIN="$TMP/git_ops.sh"
    export GIT_PLATFORM_BIN="$TMP/git_platform.sh"
    export CALL_LOG="$TMP/calls.log"
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# fixture writers
mk_issue() { # mk_issue <n> <state> <labels-csv> <body>
    local n="$1" state="$2" labels="$3" body="${4:-}"
    local lj=""; IFS=',' read -ra arr <<< "$labels"
    for l in "${arr[@]}"; do [[ -z "$l" ]] && continue; lj+="{\"name\":\"$l\"},"; done
    lj="[${lj%,}]"
    cat >"$FIXTURE_DIR/issue-$n.json" <<EOF
{"number":$n,"state":"$state","labels":$lj,"title":"issue $n","body":"$body","comments":[]}
EOF
}

@test "--help exits 0 and prints usage" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"next-issue"* ]]
    [[ "$output" == *"check-deps"* ]]
}

@test "unknown subcommand errors via err() and exits non-zero" {
    run "$SCRIPT" bogus
    [ "$status" -ne 0 ]
    [[ "$output" == *"auto-issue-dev:"* ]]
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `configs/claude/scripts/auto_issue_dev.sh`:

```bash
#!/usr/bin/env bash
# auto_issue_dev.sh - selection/dependency/flagging engine for /auto-issue-dev
#
# Wraps git_ops.sh. Picks the next opted-in ('auto-dev') issue that is ready to
# develop, skipping (and tagging) ones with unmet dependencies. Failure/dependency
# flagging is fail-open.
#
# Subcommands:
#   next-issue [--json]        First READY auto-dev issue; exit 3 when none
#   check-deps <N> [--json]    Exit 2 if issue N has unmet dependency refs
#   mark-blocked <N> <reason>  Add needs-human label + deduped comment (exit 0)
#   mark-dependency <N> <refs> Add blocked-dependency label + deduped comment (exit 0)
#
# Env seams: GIT_OPS_BIN, GIT_PLATFORM_BIN, AUTO_ISSUE_DEV_LABEL,
#            AUTO_ISSUE_DEV_DEP_LABEL, AUTO_ISSUE_DEV_FAIL_LABEL

set -euo pipefail

err() { echo "auto-issue-dev: $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_OPS_BIN="${GIT_OPS_BIN:-${SCRIPT_DIR}/git_ops.sh}"
GIT_PLATFORM_BIN="${GIT_PLATFORM_BIN:-${SCRIPT_DIR}/git_platform.sh}"
DEV_LABEL="${AUTO_ISSUE_DEV_LABEL:-auto-dev}"
DEP_LABEL="${AUTO_ISSUE_DEV_DEP_LABEL:-blocked-dependency}"
FAIL_LABEL="${AUTO_ISSUE_DEV_FAIL_LABEL:-needs-human}"

git_ops() { "${GIT_OPS_BIN}" "$@"; }

usage() {
    cat <<'USAGE'
Usage: auto_issue_dev.sh <subcommand> [args]

  next-issue [--json]          First READY auto-dev issue; exit 3 when none
  check-deps <N> [--json]      Exit 2 if issue N has unmet dependency refs
  mark-blocked <N> <reason>    Add needs-human label + deduped comment
  mark-dependency <N> <refs>   Add blocked-dependency label + deduped comment

Fail-open: mark-* always exit 0. Opt-in label: auto-dev.
USAGE
}

main() {
    local sub="${1:-}"; shift || true
    case "${sub}" in
        --help|-h|help) usage; exit 0 ;;
        *) err "unknown subcommand: ${sub:-<none>}"; usage >&2; exit 64 ;;
    esac
}

main "$@"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `chmod +x configs/claude/scripts/auto_issue_dev.sh && bats tests/bats/auto_issue_dev.bats`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/auto_issue_dev.sh tests/bats/auto_issue_dev.bats
git commit -m "feat(auto-issue-dev): script skeleton with --help and dispatch"
```

---

## Task 3: `check-deps` subcommand

**Files:**
- Modify: `configs/claude/scripts/auto_issue_dev.sh`
- Test: `tests/bats/auto_issue_dev.bats`

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/auto_issue_dev.bats`:

```bash
@test "check-deps: no dependency refs -> exit 0" {
    mk_issue 10 open auto-dev "Just a normal issue body"
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

@test "check-deps: 'blocked by #11' where #11 open -> exit 2, names ref" {
    mk_issue 10 open auto-dev "blocked by #11"
    mk_issue 11 open "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
    [[ "$output" == *"#11"* ]]
}

@test "check-deps: 'depends on #11' where #11 closed -> exit 0" {
    mk_issue 10 open auto-dev "depends on #11"
    mk_issue 11 closed "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 0 ]
}

@test "check-deps: multiple patterns, mix of met/unmet -> exit 2 lists only unmet" {
    mk_issue 10 open auto-dev "requires #11 and needs #12"
    mk_issue 11 closed "" ""
    mk_issue 12 open "" ""
    run "$SCRIPT" check-deps 10
    [ "$status" -eq 2 ]
    [[ "$output" == *"#12"* ]]
    [[ "$output" != *"#11"* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: the 4 `check-deps` tests FAIL (unknown subcommand).

- [ ] **Step 3: Write minimal implementation**

In `auto_issue_dev.sh`, add this function above `main()`:

```bash
# parse_dep_refs <text> — print unique dependency issue/PR numbers, one per line
parse_dep_refs() {
    python3 - "$1" <<'PY'
import sys, re
text = sys.argv[1] or ""
pat = re.compile(r'(?:depends on|blocked by|requires|needs)\s+#(\d+)', re.IGNORECASE)
seen = []
for m in pat.finditer(text):
    n = m.group(1)
    if n not in seen:
        seen.append(n)
print("\n".join(seen))
PY
}

# ref_met <M> — return 0 if referenced issue is closed OR PR is merged, else 1
ref_met() {
    local m="$1" view state merged
    view="$(git_ops issue-view "$m" 2>/dev/null || true)"
    if [[ -n "${view}" ]]; then
        state="$(printf '%s' "${view}" | python3 -c 'import sys,json; print((json.load(sys.stdin).get("state") or "").lower())' 2>/dev/null || true)"
        [[ "${state}" == "closed" || "${state}" == "merged" ]] && return 0
        return 1
    fi
    # Fall back to PR view (ref may be a PR number)
    view="$(git_ops pr-view "$m" 2>/dev/null || true)"
    [[ -z "${view}" ]] && return 1
    merged="$(printf '%s' "${view}" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("yes" if (d.get("merged") or (d.get("state") or "").lower()=="merged") else "no")' 2>/dev/null || echo no)"
    [[ "${merged}" == "yes" ]]
}

# cmd_check_deps <N> [--json]
cmd_check_deps() {
    local n="$1"; local json=0; [[ "${2:-}" == "--json" ]] && json=1
    [[ -n "${n}" ]] || { err "check-deps: issue number required"; return 1; }
    local body refs unmet=()
    body="$(git_ops issue-view "${n}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print((d.get("title") or "")+" \n "+(d.get("body") or ""))
except Exception: pass' || true)"
    refs="$(parse_dep_refs "${body}")"
    local m
    while IFS= read -r m; do
        [[ -z "${m}" || "${m}" == "${n}" ]] && continue
        ref_met "${m}" || unmet+=("${m}")
    done <<< "${refs}"
    if [[ ${#unmet[@]} -eq 0 ]]; then
        [[ ${json} -eq 1 ]] && echo '{"unmet":[]}'
        return 0
    fi
    if [[ ${json} -eq 1 ]]; then
        printf '{"unmet":[%s]}\n' "$(IFS=,; echo "${unmet[*]}")"
    else
        printf 'unmet dependencies for #%s: %s\n' "${n}" "$(printf '#%s ' "${unmet[@]}")"
    fi
    return 2
}
```

Then extend the `case` in `main()` (add before the `*)` arm):

```bash
        check-deps) cmd_check_deps "$@"; exit $? ;;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/auto_issue_dev.sh tests/bats/auto_issue_dev.bats
git commit -m "feat(auto-issue-dev): check-deps dependency parsing + resolution"
```

---

## Task 4: `mark-blocked` and `mark-dependency` (fail-open, deduped)

**Files:**
- Modify: `configs/claude/scripts/auto_issue_dev.sh`
- Test: `tests/bats/auto_issue_dev.bats`

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/auto_issue_dev.bats`:

```bash
@test "mark-blocked: adds needs-human label and a comment, exit 0" {
    mk_issue 10 open auto-dev ""
    run "$SCRIPT" mark-blocked 10 "tests failed"
    [ "$status" -eq 0 ]
    grep -q "issue-edit 10 .*needs-human" "$CALL_LOG"
    grep -q "issue-comment 10" "$CALL_LOG"
}

@test "mark-blocked: skips comment when marker already present (dedup)" {
    cat >"$FIXTURE_DIR/issue-10.json" <<'EOF'
{"number":10,"state":"open","labels":[{"name":"auto-dev"}],"title":"t","body":"b","comments":[{"body":"<!-- auto-issue-dev:blocked -->\nprior"}]}
EOF
    run "$SCRIPT" mark-blocked 10 "again"
    [ "$status" -eq 0 ]
    ! grep -q "issue-comment 10" "$CALL_LOG"
}

@test "mark-blocked: fail-open when label edit errors" {
    mk_issue 10 open auto-dev ""
    EDIT_RC=1 run "$SCRIPT" mark-blocked 10 "reason"
    [ "$status" -eq 0 ]
}

@test "mark-dependency: adds blocked-dependency label + comment naming refs" {
    mk_issue 10 open auto-dev ""
    run "$SCRIPT" mark-dependency 10 "#11 #12"
    [ "$status" -eq 0 ]
    grep -q "issue-edit 10 .*blocked-dependency" "$CALL_LOG"
    grep -q "issue-comment 10" "$CALL_LOG"
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: the 4 new tests FAIL.

- [ ] **Step 3: Write minimal implementation**

In `auto_issue_dev.sh`, add above `main()`:

```bash
# has_marker <N> <marker> — 0 if a comment with marker already exists
has_marker() {
    local n="$1" marker="$2" body
    body="$(git_ops issue-view "${n}" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    print("\n".join(c.get("body","") for c in (d.get("comments") or [])))
except Exception: pass' || true)"
    [[ "${body}" == *"${marker}"* ]]
}

# flag <N> <label> <marker> <comment-body> — add label + deduped comment (fail-open)
flag() {
    local n="$1" label="$2" marker="$3" comment="$4"
    [[ -n "${n}" ]] || { err "flag: issue number required"; return 0; }
    git_ops issue-edit "${n}" --add-label "${label}" >/dev/null 2>&1 \
        || err "could not add '${label}' to #${n} (continuing)"
    if has_marker "${n}" "${marker}"; then
        return 0
    fi
    printf '%s\n\n%s\n' "${marker}" "${comment}" \
        | git_ops issue-comment "${n}" --body-file - >/dev/null 2>&1 \
        || err "could not comment on #${n} (continuing)"
    return 0
}

cmd_mark_blocked() {
    local n="$1" reason="${2:-unspecified}"
    flag "${n}" "${FAIL_LABEL}" "<!-- auto-issue-dev:blocked -->" \
        "Auto-dev could not complete this issue: ${reason}. Flagged \`${FAIL_LABEL}\` for a human."
    return 0
}

cmd_mark_dependency() {
    local n="$1" refs="${2:-}"
    flag "${n}" "${DEP_LABEL}" "<!-- auto-issue-dev:dependency -->" \
        "Skipped by auto-dev: unmet dependency ${refs}. Will retry once the blocker merges and the \`${DEP_LABEL}\` label is removed."
    return 0
}
```

Note: the test stub's `git_ops issue-comment` ignores stdin, so `--body-file -` is fine in tests; in production `git_ops.sh` forwards args to `gh/glab issue comment`, which accept `--body-file -`.

Extend `main()` case (before `*)`):

```bash
        mark-blocked) cmd_mark_blocked "$@"; exit 0 ;;
        mark-dependency) cmd_mark_dependency "$@"; exit 0 ;;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/auto_issue_dev.sh tests/bats/auto_issue_dev.bats
git commit -m "feat(auto-issue-dev): mark-blocked + mark-dependency (fail-open, deduped)"
```

---

## Task 5: `next-issue` selection (oldest-first, dependency-aware)

**Files:**
- Modify: `configs/claude/scripts/auto_issue_dev.sh`
- Test: `tests/bats/auto_issue_dev.bats`

- [ ] **Step 1: Write the failing tests**

Append to `tests/bats/auto_issue_dev.bats`. `ISSUE_LIST_OUT` is the JSON the stubbed `git_ops issue-list` returns:

```bash
@test "next-issue: returns lowest-numbered ready auto-dev issue (JSON)" {
    export ISSUE_LIST_OUT='[{"number":21,"title":"b","url":"u21","labels":[{"name":"auto-dev"}]},{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open auto-dev "no deps"
    mk_issue 21 open auto-dev "no deps"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":20'* ]]
}

@test "next-issue: skips + tags a dependency-blocked candidate, returns next ready" {
    export ISSUE_LIST_OUT='[{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"}]},{"number":21,"title":"b","url":"u21","labels":[{"name":"auto-dev"}]}]'
    mk_issue 20 open auto-dev "blocked by #99"
    mk_issue 99 open "" ""
    mk_issue 21 open auto-dev "ready"
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 0 ]
    [[ "$output" == *'"number":21'* ]]
    grep -q "issue-edit 20 .*blocked-dependency" "$CALL_LOG"
}

@test "next-issue: pre-excludes already blocked-dependency-tagged issues" {
    export ISSUE_LIST_OUT='[{"number":20,"title":"a","url":"u20","labels":[{"name":"auto-dev"},{"name":"blocked-dependency"}]}]'
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'"skipped_other":1'* ]]
}

@test "next-issue: empty queue -> exit 3 with counts" {
    export ISSUE_LIST_OUT='[]'
    run "$SCRIPT" next-issue --json
    [ "$status" -eq 3 ]
    [[ "$output" == *'"ready":0'* ]]
    [[ "$output" == *'"skipped_dependency":0'* ]]
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: the 4 `next-issue` tests FAIL.

- [ ] **Step 3: Write minimal implementation**

In `auto_issue_dev.sh`, add above `main()`:

```bash
# cmd_next_issue [--json]
cmd_next_issue() {
    local json=0; [[ "${1:-}" == "--json" ]] && json=1
    local list
    list="$(git_ops issue-list --state open --label "${DEV_LABEL}" \
                --json number,title,url,labels 2>/dev/null || echo '[]')"
    [[ -z "${list}" ]] && list='[]'

    # Candidate numbers, ascending (oldest-first ~= lowest number), that are NOT
    # already tagged DEP_LABEL. Also count those excluded for that reason.
    local cand skipped_other
    cand="$(printf '%s' "${list}" | python3 -c 'import sys,json
dep=sys.argv[1]
try: items=json.load(sys.stdin)
except Exception: items=[]
ok=[i for i in items if dep not in {l["name"] for l in (i.get("labels") or [])}]
ok.sort(key=lambda i:i["number"])
print(" ".join(str(i["number"]) for i in ok))' "${DEP_LABEL}")"
    skipped_other="$(printf '%s' "${list}" | python3 -c 'import sys,json
dep=sys.argv[1]
try: items=json.load(sys.stdin)
except Exception: items=[]
print(sum(1 for i in items if dep in {l["name"] for l in (i.get("labels") or [])}))' "${DEP_LABEL}")"

    local skipped_dependency=0 n
    for n in ${cand}; do
        if out="$(cmd_check_deps "${n}" --json)"; then
            : # ready
        else
            # unmet deps -> tag + skip
            local refs
            refs="$(printf '%s' "${out}" | python3 -c 'import sys,json
try: u=json.load(sys.stdin).get("unmet",[])
except Exception: u=[]
print(" ".join("#%s"%x for x in u))' 2>/dev/null || true)"
            cmd_mark_dependency "${n}" "${refs}"
            skipped_dependency=$((skipped_dependency + 1))
            continue
        fi
        # ready candidate n — emit and exit 0
        local meta
        meta="$(git_ops issue-list --state open --label "${DEV_LABEL}" --json number,title,url 2>/dev/null \
            | python3 -c 'import sys,json
n=int(sys.argv[1]); sk=int(sys.argv[2])
try: items=json.load(sys.stdin)
except Exception: items=[]
m=next((i for i in items if i["number"]==n), {"number":n,"title":"","url":""})
print(json.dumps({"number":m["number"],"title":m.get("title",""),"url":m.get("url",""),"skipped_dependency":sk}))' "${n}" "${skipped_dependency}")"
        if [[ ${json} -eq 1 ]]; then echo "${meta}"; else echo "${n}"; fi
        return 0
    done

    # none ready
    if [[ ${json} -eq 1 ]]; then
        printf '{"ready":0,"skipped_dependency":%s,"skipped_other":%s}\n' \
            "${skipped_dependency}" "${skipped_other:-0}"
    else
        err "no ready auto-dev issues (skipped ${skipped_dependency} for deps)"
    fi
    return 3
}
```

Note `cmd_check_deps` returns 2 on unmet — in `if cmd_check_deps ...; then` the non-zero (2) takes the `else` branch, which is what we want. Guard `set -e`: wrap the call so a `return 2` does not abort the script — it is already inside an `if`, which suppresses `set -e`.

Extend `main()` case (before `*)`):

```bash
        next-issue) cmd_next_issue "$@"; exit $? ;;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bats tests/bats/auto_issue_dev.bats`
Expected: all 14 tests PASS.

- [ ] **Step 5: Run shellcheck**

Run: `shellcheck configs/claude/scripts/auto_issue_dev.sh`
Expected: no output (exit 0). Fix any warnings (quote expansions, etc.) before committing.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/auto_issue_dev.sh tests/bats/auto_issue_dev.bats
git commit -m "feat(auto-issue-dev): next-issue selection with dependency skip + counts"
```

---

## Task 6: `auto-issue-dev` skill + evals

**Files:**
- Create: `.skillshare/skills/auto-issue-dev/SKILL.md`
- Create: `.skillshare/skills/auto-issue-dev/evals/evals.json`

- [ ] **Step 1: Write the SKILL.md**

Create `.skillshare/skills/auto-issue-dev/SKILL.md`:

````markdown
---
name: auto-issue-dev
description: |
  Autonomously develop ONE opted-in ('auto-dev'-labeled) issue end-to-end: pick the
  next ready issue, branch, implement test-first, verify, and open a PR for human
  review (never merges). Dependency-blocked issues are tagged and skipped. Designed
  to run unattended in a loop (/loop /auto-issue-dev) until the queue is empty.
---

# Autonomous Issue Developer

Develop **exactly one** eligible issue per invocation, then stop. `/loop` re-runs
this skill with fresh context for the next issue.

## Critical Rules

1. **Never merge.** Stop at PR-open; a human reviews and merges.
2. **Never touch issues lacking the `auto-dev` label.** Selection is opt-in.
3. **One issue per invocation.** Do not loop inside this skill.
4. **On failure, open a DRAFT PR** (no `Closes` keyword) so a human can inspect
   partial work — never a real PR. If there are no commits, skip the draft.
5. Status sync (`planned→in-progress→needs-review`) and `Closes #N` are handled by
   the issue-linking hooks — do not hand-edit labels for the happy path.

## Procedure

1. **Preflight.** Ensure the issue hooks are enabled:
   `configs/claude/scripts/install_issue_hooks.sh --enable` (idempotent). Confirm
   `gh`/`glab` is authenticated.
2. **Select.** Run:
   `configs/claude/scripts/auto_issue_dev.sh next-issue --json`
   - Exit 3 ⇒ read `skipped_dependency`/`skipped_other` from the JSON, announce
     "eligible queue empty — stopping (skipped N dependency-blocked)", and END.
   - Exit 0 ⇒ parse `{number,title,url,skipped_dependency}`; call the issue `#N`.
3. **Branch.** `git switch -c <N>-<short-slug>` (numeric prefix links `#N`).
4. **Develop test-first.** Invoke `superpowers:test-driven-development`: write a
   failing test for the issue's acceptance criteria, implement minimally, get green.
   Keep scope to the issue.
5. **Verify.** Run `/verify`. Lint warnings are non-blocking; test or security
   failures are blocking.
6. **Outcome:**
   - **Success** → `configs/claude/scripts/git_ops.sh pr-create --title "<...>" --body "<...>"`.
     The PR hook injects `Closes #N` and moves `#N` to `needs-review`. **Stop.**
   - **Failure/stuck** → push WIP and open a **draft**:
     `git_ops.sh pr-create --draft --title "[WIP] <...>" --body "Partial; needs human."`
     then `auto_issue_dev.sh mark-blocked <N> "<one-line reason>"`.
7. **Summary.** Print one line: issue, outcome (PR # or draft), and skip count.

## Notes

- Dependency-blocked issues are detected and tagged `blocked-dependency` by
  `next-issue`; you never see them.
- This skill writes code (allowed tools include Edit/Write); keep diffs scoped to
  the selected issue.
````

- [ ] **Step 2: Write evals.json**

Create `.skillshare/skills/auto-issue-dev/evals/evals.json`:

```json
{
  "skill_name": "auto-issue-dev",
  "evals": [
    {
      "id": 0,
      "prompt": "pick up the next auto-dev issue and build it, open a PR but don't merge",
      "expected_output": "Selects the lowest-numbered ready auto-dev issue via auto_issue_dev.sh next-issue, branches with the issue-number prefix, implements test-first, verifies, and opens a (non-draft) PR that the #345 hook links with Closes #N. Stops at PR-open; never merges.",
      "files": []
    },
    {
      "id": 1,
      "prompt": "run the autonomous issue developer until there's nothing left in the queue",
      "expected_output": "Explains it develops one issue per invocation and is driven unattended via /loop /auto-issue-dev, terminating when next-issue exits 3 (empty queue), reporting how many issues were skipped as dependency-blocked.",
      "files": []
    },
    {
      "id": 2,
      "prompt": "auto-develop issue work but if something has an unmerged dependency, don't touch it",
      "expected_output": "Notes that next-issue auto-detects unmet dependencies (depends on/blocked by/requires/needs #M), tags those issues blocked-dependency, comments naming the blocker, and excludes them from the loop scope rather than developing them.",
      "files": []
    }
  ]
}
```

- [ ] **Step 3: Validate evals.json**

Run: `python3 -c "import json; d=json.load(open('.skillshare/skills/auto-issue-dev/evals/evals.json')); assert d['skill_name']=='auto-issue-dev'; assert len(d['evals'])==3; print('evals OK')"`
Expected: `evals OK`.

- [ ] **Step 4: Commit**

```bash
git add .skillshare/skills/auto-issue-dev/
git commit -m "feat(auto-issue-dev): skill definition + evals"
```

---

## Task 7: Wiring — tool_policies, Cursor rule, docs

**Files:**
- Modify: `configs/claude/config/command_config.yml`
- Create: `configs/cursor/rules/auto-issue-dev.mdc` (generated)
- Modify: `docs/COMMANDS.md`

- [ ] **Step 1: Add tool_policies entry**

In `configs/claude/config/command_config.yml`, under `tool_policies:`, add (alphabetical order — near the `a*` entries):

```yaml
  auto-issue-dev:
    allowed:
      - Bash       # auto_issue_dev.sh, git_ops.sh, install_issue_hooks.sh, git, gh/glab
      - Read
      - Edit       # writes code for the selected issue
      - Write
      - Skill      # test-driven-development, verify
    forbidden: []
    parallel_agents: never
    validation_tier: 1
```

- [ ] **Step 2: Validate YAML**

Run:
```bash
yamllint configs/claude/config/command_config.yml
python3 -c "import yaml; d=yaml.safe_load(open('configs/claude/config/command_config.yml')); assert 'auto-issue-dev' in d['tool_policies']; print('policy OK')"
```
Expected: yamllint exits 0; prints `policy OK`.

- [ ] **Step 3: Generate the Cursor rule**

Run: `configs/claude/scripts/generate_cursor_rules.sh`
Expected: creates `configs/cursor/rules/auto-issue-dev.mdc` (auto-generated from the SKILL.md). Verify:
`test -f configs/cursor/rules/auto-issue-dev.mdc && head -3 configs/cursor/rules/auto-issue-dev.mdc`
Expected: file exists with frontmatter `description:` line.

- [ ] **Step 4: Add docs/COMMANDS.md entry**

In `docs/COMMANDS.md`, find the issue-management section (search for `issue-prioritize`) and add a row/entry adjacent to it:

```markdown
### `/auto-issue-dev`

Autonomously develops one opted-in (`auto-dev`-labeled) issue end-to-end —
selects the next ready issue, implements test-first, verifies, and opens a PR
(never merges). Dependency-blocked issues are tagged `blocked-dependency` and
skipped. Run unattended with `/loop /auto-issue-dev`; stops when the queue is
empty. Backed by `configs/claude/scripts/auto_issue_dev.sh`.
```

- [ ] **Step 5: Commit**

```bash
git add configs/claude/config/command_config.yml configs/cursor/rules/auto-issue-dev.mdc docs/COMMANDS.md
git commit -m "feat(auto-issue-dev): tool_policies, cursor rule, docs wiring"
```

---

## Task 8: Full verification + manual e2e

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run:
```bash
bats tests/bats/auto_issue_dev.bats
shellcheck configs/claude/scripts/auto_issue_dev.sh
yamllint configs/claude/config/labels.yml configs/claude/config/command_config.yml
```
Expected: bats all PASS; shellcheck clean; yamllint exit 0.

- [ ] **Step 2: Sync skills to home so `/auto-issue-dev` is invocable**

Run: `sync-skills` (or `./bootstrap.sh --skip-install --skip-auth --force ...` preserving toggles)
Expected: `auto-issue-dev` appears under `~/.claude/skills/`.

- [ ] **Step 3: Manual e2e (throwaway issues, mirrors the issue-closer e2e)**

In a sandbox or with disposable issues:
- Create issue A labeled `auto-dev` (no deps) → run `/auto-issue-dev` →
  expect a real PR with `Closes #A`, issue → `needs-review`. Confirm via
  `gh pr view <PR> --json closingIssuesReferences`.
- Create issue B labeled `auto-dev` with body `blocked by #A` while #A is open →
  run `auto_issue_dev.sh next-issue --json` → expect B skipped, tagged
  `blocked-dependency`, comment present.
- Create an unbuildable issue C labeled `auto-dev` → run `/auto-issue-dev` →
  expect a **draft** PR + `needs-human`.
- Clean up: close issues/PRs, delete branches.

- [ ] **Step 4: Final commit (if any cleanup) and open PR for the feature**

```bash
git_ops.sh pr-create --title "feat: autonomous issue developer (/auto-issue-dev)" \
  --body "Implements docs/superpowers/specs/2026-06-14-auto-issue-dev-design.md"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** opt-in label (Task 1, Task 5 filter), dependency detection
  (Task 3, Task 5), failure → draft + needs-human (Task 6 skill + Task 4),
  stop-when-empty (Task 5 exit 3 + Task 6), stop-at-PR-open (Task 6 rule 1),
  `/loop` driver (Task 6 + docs), labels (Task 1), helper subcommands
  (Tasks 2–5), wiring/evals/cursor/docs (Tasks 6–7), tests (every task + Task 8).
  No spec requirement is unmapped.
- **Placeholder scan:** every code/step shows actual content; no TBD/TODO.
- **Type/name consistency:** subcommands `next-issue`/`check-deps`/`mark-blocked`/
  `mark-dependency`, env vars `DEV_LABEL`/`DEP_LABEL`/`FAIL_LABEL`, markers
  `auto-issue-dev:blocked`/`auto-issue-dev:dependency`, and exit codes
  (0 ready / 2 unmet / 3 empty) are used identically across tasks and the skill.
