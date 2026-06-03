#!/usr/bin/env bats
# Tests for configs/claude/scripts/version_pin.sh

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/configs/claude/scripts/version_pin.sh"

setup() {
    export BATS_TMPDIR="${BATS_TMPDIR:-/tmp}"
    SANDBOX=$(mktemp -d "$BATS_TMPDIR/version_pin.XXXXXX")
    export VERSION_PIN_CONFIG="$REPO_ROOT/configs/claude/config/command_config.yml"

    # Deterministic, offline stub resolver.
    cat > "$SANDBOX/resolver.sh" <<'EOF'
#!/usr/bin/env bash
eco="$1"; name="$2"; current="$3"; requested="$4"
case "$eco" in
  pip) printf '%s\t%s\n' "${requested:-2.31.0}" "abc123" ;;
  docker)
    if [[ -n "$requested" ]]; then printf '%s\t%s\n' "$requested" "sha256:dead"
    elif [[ -n "$current" && "$current" != latest ]]; then printf '%s\t%s\n' "$current" "sha256:dead"
    else printf '%s\t%s\n' "16.2" "sha256:cafe"; fi ;;
  *) exit 1 ;;
esac
EOF
    chmod +x "$SANDBOX/resolver.sh"
    export VERSION_PIN_RESOLVER="$SANDBOX/resolver.sh"
}

teardown() {
    [[ -n "$SANDBOX" && -d "$SANDBOX" ]] && rm -rf "$SANDBOX"
}

@test "pip: unpinned requirement is rewritten to version + hash (on-demand)" {
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    run cat "$SANDBOX/requirements.txt"
    assert_output "requests==2.31.0 --hash=sha256:abc123"
}

@test "pip: pin without hash is upgraded to include a hash" {
    printf 'flask==2.0.0\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    run cat "$SANDBOX/requirements.txt"
    assert_output "flask==2.31.0 --hash=sha256:abc123"
}

@test "pip: --requested pins the exact requested version" {
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt" --requested requests=9.9.9
    assert_success
    run cat "$SANDBOX/requirements.txt"
    assert_output "requests==9.9.9 --hash=sha256:abc123"
}

@test "--check is warn-only: reports violations, exits 1, makes no edits" {
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt" --check
    assert_failure
    assert_output --partial "violation"
    run cat "$SANDBOX/requirements.txt"
    assert_output "requests"
}

@test "compliant entry is left unchanged and counted compliant" {
    printf 'good==1.0 --hash=sha256:zzz\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    assert_output --partial "1 compliant"
    run cat "$SANDBOX/requirements.txt"
    assert_output "good==1.0 --hash=sha256:zzz"
}

@test "bypass marker preserves the line byte-for-byte" {
    printf 'legacy  # version-pin:ignore\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    assert_output --partial "bypassed"
    run cat "$SANDBOX/requirements.txt"
    assert_output "legacy  # version-pin:ignore"
}

@test "second run is idempotent (no further changes)" {
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    first=$(cat "$SANDBOX/requirements.txt")
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    assert_output --partial "0 violations"
    second=$(cat "$SANDBOX/requirements.txt")
    [ "$first" = "$second" ]
}

@test "unresolved (resolver fails) is a non-fatal warning, file untouched" {
    cat > "$SANDBOX/fail.sh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
    chmod +x "$SANDBOX/fail.sh"
    export VERSION_PIN_RESOLVER="$SANDBOX/fail.sh"
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    assert_output --partial "unresolved"
    run cat "$SANDBOX/requirements.txt"
    assert_output "requests"
}

@test "docker-compose: latest tag becomes specific version + digest" {
    printf 'services:\n  db:\n    image: postgres:latest\n' > "$SANDBOX/docker-compose.yaml"
    run "$SCRIPT" "$SANDBOX/docker-compose.yaml"
    assert_success
    run cat "$SANDBOX/docker-compose.yaml"
    assert_output --partial "image: postgres:16.2@sha256:cafe"
}

@test "docker-compose: already-digested image is left unchanged" {
    printf 'services:\n  x:\n    image: nginx:1.0@sha256:abc\n' > "$SANDBOX/docker-compose.yaml"
    run "$SCRIPT" "$SANDBOX/docker-compose.yaml"
    assert_success
    assert_output --partial "1 compliant"
    run cat "$SANDBOX/docker-compose.yaml"
    assert_output --partial "image: nginx:1.0@sha256:abc"
}

@test "hook-scoping: a recognized file IS processed (SC-003 positive)" {
    printf 'requests\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt" --check
    assert_failure
    assert_output --partial "requirements.txt"
}

@test "hook-scoping: an unrelated file is NOT processed (SC-003 negative)" {
    printf 'just some prose\n' > "$SANDBOX/README.md"
    run "$SCRIPT" "$SANDBOX/README.md" --check
    assert_success
    assert_output --partial "no applicable rules"
    refute_output --partial " -> "
}

@test "pip: extras and environment markers are preserved on rewrite" {
    printf 'requests[socks]>=2 ; python_version < "3.12"\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    run cat "$SANDBOX/requirements.txt"
    assert_output 'requests[socks]==2.31.0; python_version < "3.12" --hash=sha256:abc123'
}

@test "pip: hash required but unobtainable -> unresolved, file untouched" {
    cat > "$SANDBOX/nohash.sh" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == pip ]] && printf '%s\t\n' "2.31.0" || exit 1
EOF
    chmod +x "$SANDBOX/nohash.sh"
    export VERSION_PIN_RESOLVER="$SANDBOX/nohash.sh"
    printf 'flask\n' > "$SANDBOX/requirements.txt"
    run "$SCRIPT" "$SANDBOX/requirements.txt"
    assert_success
    assert_output --partial "unresolved"
    assert_output --partial "requires one"
    run cat "$SANDBOX/requirements.txt"
    assert_output "flask"
}

@test "dockerfile: FROM --platform flag and AS stage are preserved" {
    printf 'FROM --platform=linux/amd64 node:20 AS build\n' > "$SANDBOX/Dockerfile"
    run "$SCRIPT" "$SANDBOX/Dockerfile"
    assert_success
    run cat "$SANDBOX/Dockerfile"
    assert_output "FROM --platform=linux/amd64 node:20@sha256:dead AS build"
}

@test "docker: registry host:port is not mistaken for a tag" {
    printf 'services:\n  app:\n    image: registry.internal:5000/team/app:1.2\n' > "$SANDBOX/docker-compose.yaml"
    run "$SCRIPT" "$SANDBOX/docker-compose.yaml"
    assert_success
    run cat "$SANDBOX/docker-compose.yaml"
    assert_output --partial "image: registry.internal:5000/team/app:1.2@sha256:dead"
}

@test "docker: digest required but empty -> unresolved, file untouched" {
    cat > "$SANDBOX/nodigest.sh" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == docker ]] && printf '%s\t\n' "1.0" || exit 1
EOF
    chmod +x "$SANDBOX/nodigest.sh"
    export VERSION_PIN_RESOLVER="$SANDBOX/nodigest.sh"
    printf 'services:\n  app:\n    image: redis:7\n' > "$SANDBOX/docker-compose.yaml"
    run "$SCRIPT" "$SANDBOX/docker-compose.yaml"
    assert_success
    assert_output --partial "unresolved"
    run cat "$SANDBOX/docker-compose.yaml"
    assert_output --partial "image: redis:7"
}

@test "directory scan is config-driven (finds recognized files in a tree)" {
    mkdir -p "$SANDBOX/sub"
    printf 'requests\n' > "$SANDBOX/sub/requirements.txt"
    run "$SCRIPT" "$SANDBOX" --check
    assert_failure
    assert_output --partial "sub/requirements.txt"
}
