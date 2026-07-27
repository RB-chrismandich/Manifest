#!/usr/bin/env bats
# Tests for configs/claude/scripts/lint_on_edit_hook.sh
# Verifies contract guarantees G1-G8 (specs/366-coding-standards/contracts/edit-time-hook.md).

SCRIPT="$BATS_TEST_DIRNAME/../../configs/claude/scripts/lint_on_edit_hook.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    TMP=$(mktemp -d "$BATS_TMPDIR/lint_on_edit.XXXXXX")
}
teardown() { [[ -n "$TMP" && -d "$TMP" ]] && rm -rf "$TMP"; }

# Build a PostToolUse JSON payload for a given file path (JSON-safe encoding so
# paths containing quotes/backslashes can never produce malformed JSON).
payload() { python3 -c "import json,sys; print(json.dumps({'tool_input':{'file_path':sys.argv[1]}}))" "$1"; }

# --- CLI surface ---

@test "--help exits 0 and prints usage" {
    run "$SCRIPT" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"advisory"* ]] || return 1
    [[ "$output" == *"Dispatch"* ]]
}

# --- G7: bad / empty payload ---

@test "G7: empty stdin exits 0" {
    run bash -c "printf '' | '$SCRIPT'"
    [ "$status" -eq 0 ]
}

@test "G7: malformed JSON exits 0" {
    run bash -c "printf 'not json{' | '$SCRIPT'"
    [ "$status" -eq 0 ]
}

@test "missing file path exits 0" {
    run bash -c "printf '{}' | '$SCRIPT'"
    [ "$status" -eq 0 ]
}

# --- G1: never blocks (exit 0 even with violations) + G4: dispatch ---

@test "G1/G4: shell file with a violation -> exit 0, finding on stderr" {
    f="$TMP/bad.sh"
    printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"   # SC2164/SC2086   # SC2086 unquoted
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lint-on-edit: $f"* ]]
}

@test "G4: python file with a violation -> ruff finding on stderr" {
    command -v ruff >/dev/null 2>&1 || skip "ruff not installed"
    f="$TMP/bad.py"
    printf 'import os\n' > "$f"   # F401 unused import
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lint-on-edit: $f"* ]]
}

@test "G4: invalid JSON file -> json.load finding on stderr" {
    f="$TMP/bad.json"
    printf '{ "a": ' > "$f"   # truncated
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lint-on-edit: $f"* ]]
}

@test "G4: yaml file with a violation -> yamllint finding on stderr" {
    command -v yamllint >/dev/null 2>&1 || skip "yamllint not installed"
    f="$TMP/bad.yaml"
    printf 'a: 1\n a: 2\n' > "$f"   # bad indentation / dup
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lint-on-edit: $f"* ]]
}

@test "clean shell file -> exit 0, no finding" {
    f="$TMP/ok.sh"
    printf '#!/usr/bin/env bash\nfoo=1\necho "$foo"\n' > "$f"
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"lint-on-edit:"* ]]
}

# --- G2: never mutates the file ---

@test "G2: file content is unchanged after linting" {
    f="$TMP/bad.sh"
    printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"   # SC2164/SC2086
    before=$(shasum "$f" | awk '{print $1}')
    bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT'" >/dev/null 2>&1
    after=$(shasum "$f" | awk '{print $1}')
    [ "$before" = "$after" ]
}

# --- G3: fail-open on missing tool ---

@test "G3: missing linter -> exit 0, no error (fail open)" {
    # Build a minimal PATH containing only the hook's helpers (python3, tr,
    # dirname, git) but NOT shellcheck/ruff, so the dispatched linter is
    # genuinely absent on ANY runner. (We cannot just exclude homebrew paths:
    # GitHub ubuntu runners ship shellcheck in /usr/bin.)
    fakebin="$TMP/bin"; mkdir -p "$fakebin"
    for t in python3 tr dirname git; do
        p="$(command -v "$t")" && ln -s "$p" "$fakebin/$t"
    done
    bash_bin="$(command -v bash)"
    f="$TMP/bad.sh"
    printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"   # SC2164/SC2086
    run bash -c "printf '%s' '$(payload "$f")' | PATH='$fakebin' '$bash_bin' '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"command not found"* ]] || return 1
    [[ "$output" != *"lint-on-edit:"* ]]   # shellcheck absent -> nothing reported
}

# --- G5: excluded paths ---

@test "G5: file under templates/scaffold is skipped" {
    mkdir -p "$TMP/templates/scaffold"
    f="$TMP/templates/scaffold/bad.sh"
    printf '#!/usr/bin/env bash\ndir=$1\ncd $dir\n' > "$f"   # SC2164/SC2086
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"lint-on-edit:"* ]]
}

# --- G6: unknown extension ---

@test "G6: unknown extension is a no-op" {
    f="$TMP/notes.txt"
    printf 'hello world\n' > "$f"
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"lint-on-edit:"* ]]
}

# --- markdown fail-open (markdownlint commonly absent) ---

@test "markdown file: exits 0 whether or not markdownlint is installed" {
    f="$TMP/doc.md"
    printf '#Heading\n\n\n' > "$f"
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
}

@test "G4: .mdc dispatches to markdownlint when available" {
    command -v markdownlint >/dev/null 2>&1 || skip "markdownlint not installed"
    f="$TMP/rule.mdc"
    printf '#Heading without space\n\nsome text\n' > "$f"
    run bash -c "printf '%s' '$(payload "$f")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"lint-on-edit: $f"* ]]
}

# --- Line caps (docs_lint.py): opt-in per repo, reports only when over ---

# Build a throwaway git repo at $1 that opts into caps by shipping a limits
# file at the path the hook looks for.
cap_repo() {
    local root="$1"
    mkdir -p "$root/configs/claude/config" "$root/docs"
    git -C "$root" init -q
    cat > "$root/configs/claude/config/doc_limits.yml" << 'YML'
---
defaults: {max_lines: 20, warn_at: 0.8}
types: {hub: {max_lines: 5}}
classify:
  - {glob: "**/docs/README.md", type: hub}
exempt: {globs: [], markers: ["DO NOT EDIT"]}
overrides: {type_marker: "doc-type:", limit_marker: "doc-limit:"}
fluff: {phrases: [], structure: {}}
YML
}

# Write $2 lines of filler markdown to $1.
fill_doc() {
    local path="$1" lines="$2" i
    : > "$path"
    for ((i = 1; i <= lines; i++)); do printf 'line %d\n' "$i" >> "$path"; done
}

@test "caps: an over-cap markdown file reports the overage on stderr, exit 0" {
    cap_repo "$TMP/repo"
    fill_doc "$TMP/repo/docs/GUIDE.md" 40
    run bash -c "printf '%s' '$(payload "$TMP/repo/docs/GUIDE.md")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"OVER (+20)"* ]] || { echo "$output"; false; }
}

@test "caps: a within-cap markdown file emits nothing" {
    # docs_lint.py always prints a summary; an advisory that fires on every
    # write is one people stop reading, so the hook must stay silent here.
    cap_repo "$TMP/repo"
    fill_doc "$TMP/repo/docs/GUIDE.md" 5
    run bash -c "printf '%s' '$(payload "$TMP/repo/docs/GUIDE.md")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"docs_lint"* ]] || { echo "$output"; false; }
    [[ "$output" != *"OVER"* ]] || { echo "$output"; false; }
}

@test "caps: per-type classification is applied, not just the default" {
    cap_repo "$TMP/repo"
    fill_doc "$TMP/repo/docs/README.md" 10   # under default 20, over hub 5
    run bash -c "printf '%s' '$(payload "$TMP/repo/docs/README.md")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"hub"* && "$output" == *"OVER (+5)"* ]] || { echo "$output"; false; }
}

@test "caps: a repo with no doc_limits.yml is never nagged (opt-in)" {
    # The hook fires on every .md write anywhere, including unrelated projects.
    mkdir -p "$TMP/plain"
    git -C "$TMP/plain" init -q
    fill_doc "$TMP/plain/BIG.md" 400
    run bash -c "printf '%s' '$(payload "$TMP/plain/BIG.md")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"OVER"* ]] || { echo "$output"; false; }
}

@test "caps: .mdc is excluded (cursor rules are generated)" {
    cap_repo "$TMP/repo"
    fill_doc "$TMP/repo/docs/rule.mdc" 400
    run bash -c "printf '%s' '$(payload "$TMP/repo/docs/rule.mdc")' | '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"OVER"* ]] || { echo "$output"; false; }
}

@test "caps: G2 holds — an over-cap file is not mutated" {
    cap_repo "$TMP/repo"
    fill_doc "$TMP/repo/docs/GUIDE.md" 40
    before="$(md5 -q "$TMP/repo/docs/GUIDE.md" 2> /dev/null || md5sum "$TMP/repo/docs/GUIDE.md" | cut -d' ' -f1)"
    run bash -c "printf '%s' '$(payload "$TMP/repo/docs/GUIDE.md")' | '$SCRIPT' 2>&1"
    after="$(md5 -q "$TMP/repo/docs/GUIDE.md" 2> /dev/null || md5sum "$TMP/repo/docs/GUIDE.md" | cut -d' ' -f1)"
    [ "$before" = "$after" ]
}

# --- G8: macOS Bash 3.2 safety (run the hook under /bin/bash) ---

@test "G8: runs under macOS /bin/bash (3.2) -> exit 0" {
    [ -x /bin/bash ] || skip "/bin/bash not present"
    run /bin/bash "$SCRIPT" --help
    [ "$status" -eq 0 ]
    f="$TMP/ok.sh"
    printf '#!/usr/bin/env bash\nfoo=1\necho "$foo"\n' > "$f"
    run bash -c "printf '%s' '$(payload "$f")' | /bin/bash '$SCRIPT' 2>&1"
    [ "$status" -eq 0 ]
}
