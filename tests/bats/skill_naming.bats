#!/usr/bin/env bats
# Skill naming taxonomy conformance gate (specs/480-skill-naming-taxonomy, #478).
#
# Every skill in .apm/skills/ must be named <purpose>-<verb>[-<qualifier>]:
# lowercase a-z0-9 tokens, 2-4 tokens, first token(s) drawn from the domain
# vocabulary in docs/SKILL-NAMING.md — unless listed in that doc's exception
# block. Frontmatter name: must always equal the directory name.
#
# If this test fails on a new skill: rename it per docs/SKILL-NAMING.md, or (rare)
# add a domain token / exception there WITH rationale in the same PR.

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)"
SKILLS_DIR="$REPO_ROOT/.apm/skills"
NAMING_DOC="$REPO_ROOT/docs/SKILL-NAMING.md"
NAMING_DOC_DIR="$REPO_ROOT/docs/skill-naming"

# A doc path is an API here. The domain vocabulary moved to its own page when
# SKILL-NAMING.md was split to fit the docs concision caps, and the gate kept
# reading only the hub: the vocabulary came back empty and every skill looked
# like a violation, with no character of content lost. So the gate reads the
# whole subject tree — the hub plus every sub-page it fans out to — and a block
# may live in any of them. Moving one again is a no-op for this gate.
naming_doc_files() {
    local f
    printf '%s\n' "$NAMING_DOC"
    for f in "$NAMING_DOC_DIR"/*.md; do
        [ -f "$f" ] && printf '%s\n' "$f"
    done
}

# Extract one-token-per-line list from a fenced block between
# "<!-- skill-naming:<section> -->" and "<!-- /skill-naming:<section> -->",
# wherever among the naming docs that block currently lives.
extract_block() {
    local section="$1" f
    local -a docs=()
    while IFS= read -r f; do
        [ -n "$f" ] && docs+=("$f")
    done <<< "$(naming_doc_files)"

    awk -v start="<!-- skill-naming:${section} -->" \
        -v end="<!-- /skill-naming:${section} -->" '
        FNR == 1    {inside=0}
        $0 == start {inside=1; next}
        $0 == end   {inside=0}
        inside && $0 !~ /^```/ && NF {print $1}
    ' "${docs[@]}"
}

# Emit the skill directories under $1 (one trailing-slash path per line). Only
# real skills — directories containing a SKILL.md — count; a stray directory
# such as a rename-leftover __pycache__ orphan is not a skill and is skipped.
skill_dirs() {
    local root="$1" dir
    for dir in "$root"/*/; do
        [ -f "$dir/SKILL.md" ] && printf '%s\n' "$dir"
    done
}

# Emit naming-taxonomy violations (one "name: reason" per line) for the skills
# under $1, given newline-lists of domain tokens ($2) and exceptions ($3).
naming_violations() {
    local root="$1" domains="$2" exceptions="$3"
    local dir name matched domain violations=""
    while IFS= read -r dir; do
        [ -n "$dir" ] || continue
        name="$(basename "$dir")"

        if printf '%s\n' "$exceptions" | grep -qx "$name"; then
            continue
        fi

        # Shape: lowercase alnum tokens, single hyphens, 2-4 tokens.
        if ! printf '%s' "$name" | grep -qE '^[a-z0-9]+(-[a-z0-9]+){1,3}$'; then
            violations+="$name: not 2-4 lowercase tokens joined by single hyphens"$'\n'
            continue
        fi

        # First token(s) must be a vocabulary domain.
        matched=false
        while IFS= read -r domain; do
            if [ "$name" != "$domain" ] && [[ "$name" == "$domain"-* ]]; then
                matched=true
                break
            fi
        done <<< "$domains"
        if [ "$matched" = false ]; then
            violations+="$name: first token not in the domain vocabulary"$'\n'
        fi
    done <<< "$(skill_dirs "$root")"
    printf '%s' "$violations"
}

@test "naming doc provides non-empty domain and exception blocks" {
    [ -f "$NAMING_DOC" ]
    local domains exceptions
    domains=$(extract_block domains)
    exceptions=$(extract_block exceptions)
    [ -n "$domains" ]
    [ -n "$exceptions" ]
}

@test "every skill-naming marker block lives in a file the gate reads" {
    local readable stray="" hit file
    readable="$(naming_doc_files)"

    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        file="${hit%%:*}"
        printf '%s\n' "$readable" | grep -qxF "$file" || stray+="$file"$'\n'
    done <<< "$(grep -rl -- '<!-- skill-naming:' "$REPO_ROOT/docs" || true)"

    if [ -n "$stray" ]; then
        echo "skill-naming marker blocks in files this gate does not parse:" >&2
        printf '%s' "$stray" >&2
        echo "Move them under docs/skill-naming/, or extend naming_doc_files()." >&2
        return 1
    fi
}

@test "every skill name conforms to <purpose>-<verb>[-<qualifier>] or is excepted" {
    local domains exceptions violations
    domains=$(extract_block domains)
    exceptions=$(extract_block exceptions)

    violations="$(naming_violations "$SKILLS_DIR" "$domains" "$exceptions")"

    if [ -n "$violations" ]; then
        echo "Skill names violating docs/SKILL-NAMING.md (<purpose>-<verb>[-<qualifier>]):" >&2
        printf '%s' "$violations" >&2
        echo "Rename the skill, or add a domain/exception in docs/SKILL-NAMING.md with rationale." >&2
        return 1
    fi
}

@test "naming gate ignores SKILL.md-less dirs (rename orphan) but still flags real skills" {
    local tmp domains exceptions
    tmp="$(mktemp -d)"
    # Orphaned rename-leftover: only a stale __pycache__, no SKILL.md. A prior
    # skill rename (e.g. post-pr-review-monitor -> pr-monitor) leaves this behind
    # because git cannot delete untracked bytecode; it must NOT be gated.
    mkdir -p "$tmp/post-pr-review-monitor/scripts/__pycache__"
    : > "$tmp/post-pr-review-monitor/scripts/__pycache__/pr_create_trigger.cpython-314.pyc"
    # A real skill (has SKILL.md) with a non-vocabulary first token must still be caught.
    mkdir -p "$tmp/zzznope-verb"
    printf 'name: zzznope-verb\n' > "$tmp/zzznope-verb/SKILL.md"

    domains=$(extract_block domains)
    exceptions=$(extract_block exceptions)
    local output
    output="$(naming_violations "$tmp" "$domains" "$exceptions")"
    rm -rf "$tmp"

    if printf '%s' "$output" | grep -q "post-pr-review-monitor"; then
        echo "orphan dir was gated as a skill: $output" >&2
        return 1
    fi
    if ! printf '%s' "$output" | grep -q "zzznope-verb"; then
        echo "enforcement regressed — real violation not reported: $output" >&2
        return 1
    fi
}

@test "every skill's frontmatter name matches its directory name" {
    local mismatches="" name fm
    for dir in "$SKILLS_DIR"/*/; do
        name="$(basename "$dir")"
        [ -f "$dir/SKILL.md" ] || continue
        fm=$(awk '/^name:/{print $2; exit}' "$dir/SKILL.md")
        if [ "$fm" != "$name" ]; then
            mismatches+="$name: frontmatter name '$fm'"$'\n'
        fi
    done
    if [ -n "$mismatches" ]; then
        echo "Frontmatter name: must equal the skill directory name:" >&2
        printf '%s' "$mismatches" >&2
        return 1
    fi
}

@test "exception list stays pruned to skills that exist" {
    local stale="" name
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        if [ ! -d "$SKILLS_DIR/$name" ]; then
            stale+="$name"$'\n'
        fi
    done <<< "$(extract_block exceptions)"
    if [ -n "$stale" ]; then
        echo "Exception entries in docs/SKILL-NAMING.md with no matching skill (prune them):" >&2
        printf '%s' "$stale" >&2
        return 1
    fi
}
