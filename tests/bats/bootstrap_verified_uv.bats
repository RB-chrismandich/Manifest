#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

INSTALL_LIB="$BATS_TEST_DIRNAME/../../bootstrap/lib/install.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/manifest_uv.XXXXXX")
    export HOME="$SANDBOX/home"
    target="aarch64-apple-darwin"
    release_dir="$SANDBOX/release/uv-$target"
    mkdir -p "$HOME/.local/bin" "$SANDBOX/bin" "$release_dir"
    printf '#!/bin/sh\necho verified\n' > "$release_dir/uv"
    chmod +x "$release_dir/uv"
    tar -czf "$SANDBOX/release/archive.tar.gz" -C "$SANDBOX/release" "uv-$target"
    sha256sum "$SANDBOX/release/archive.tar.gz" | awk '{print $1}' > "$SANDBOX/release/archive.sha256"
    cat > "$SANDBOX/bin/uv" <<'EOF'
#!/bin/sh
echo ambient
EOF
    chmod +x "$SANDBOX/bin/uv"
    cat > "$SANDBOX/bin/curl" <<EOF
#!/bin/sh
out=""
while [ "\$#" -gt 0 ]; do
  if [ "\$1" = "-o" ]; then out="\$2"; shift 2; continue; fi
  shift
done
case "\$out" in *.sha256) cp "$SANDBOX/release/archive.sha256" "\$out" ;; *) cp "$SANDBOX/release/archive.tar.gz" "\$out" ;; esac
EOF
    chmod +x "$SANDBOX/bin/curl"
}

teardown() { rm -rf "$SANDBOX"; }

repack_archive() {
    python3 - "$SANDBOX/release/archive.tar.gz" "$target" "$1" <<'PY'
import sys
import tarfile

archive, target, kind = sys.argv[1:]
path = f"uv-{target}/uv"
with tarfile.open(archive, "w:gz") as tar:
    if kind == "symlink":
        payload = tarfile.TarInfo(f"uv-{target}/payload")
        payload.size = len(b"#!/bin/sh\nexit 0\n")
        payload.mode = 0o755
        tar.addfile(payload, __import__("io").BytesIO(b"#!/bin/sh\nexit 0\n"))
        entry = tarfile.TarInfo(path)
        entry.type = tarfile.SYMTYPE
        entry.linkname = "payload"
        entry.mode = 0o755
        tar.addfile(entry)
    elif kind == "hardlink":
        payload = tarfile.TarInfo(f"uv-{target}/payload")
        payload.size = len(b"#!/bin/sh\nexit 0\n")
        payload.mode = 0o755
        tar.addfile(payload, __import__("io").BytesIO(b"#!/bin/sh\nexit 0\n"))
        entry = tarfile.TarInfo(path)
        entry.type = tarfile.LNKTYPE
        entry.linkname = f"uv-{target}/payload"
        entry.mode = 0o755
        tar.addfile(entry)
    elif kind == "special":
        entry = tarfile.TarInfo(path)
        entry.type = tarfile.FIFOTYPE
        entry.mode = 0o755
        tar.addfile(entry)
    elif kind == "duplicate":
        for body in (b"#!/bin/sh\nexit 0\n", b"#!/bin/sh\nexit 1\n"):
            entry = tarfile.TarInfo(path)
            entry.size = len(body)
            entry.mode = 0o755
            tar.addfile(entry, __import__("io").BytesIO(body))
    else:
        raise SystemExit(f"unsupported archive kind: {kind}")
PY
}

run_verified_uv_check() {
    run env PATH="$SANDBOX/bin:/usr/bin:/bin" HOME="$HOME" bash -c '
        print_step() { :; }; print_success() { :; }; print_warning() { echo "$*"; }
        command_exists() { command -v "$1" >/dev/null 2>&1; }
        source "'"$INSTALL_LIB"'"
        _uv_release_target() { echo "'"$target"'"; }
        _uv_archive_sha256() { shasum -a 256 "'"$SANDBOX"'/release/archive.tar.gz" | awk "{print \$1}"; }
        _uv_executable_sha256() { echo ""; }
        check_uv
    '
}

@test "check_uv replaces an ambient same-version binary with verified pinned bytes" {
    run_verified_uv_check
    assert_success

    run "$HOME/.local/bin/uv"
    assert_success
    assert_output "verified"
}

@test "check_uv replaces a destination symlink without following it" {
    printf 'user file\n' > "$SANDBOX/victim"
    ln -s "$SANDBOX/victim" "$HOME/.local/bin/uv"

    run_verified_uv_check

    assert_success
    assert_equal "$(cat "$SANDBOX/victim")" "user file"
    [[ ! -L "$HOME/.local/bin/uv" ]] || return 1
    run "$HOME/.local/bin/uv"
    assert_success
    assert_output "verified"
}

@test "check_uv removes an executable whose locked digest does not match" {
    run env PATH="$SANDBOX/bin:/usr/bin:/bin" HOME="$HOME" bash -c '
        print_step() { :; }; print_success() { :; }; print_warning() { echo "$*"; }
        command_exists() { command -v "$1" >/dev/null 2>&1; }
        source "'"$INSTALL_LIB"'"
        _uv_release_target() { echo "'"$target"'"; }
        _uv_archive_sha256() { shasum -a 256 "'"$SANDBOX"'/release/archive.tar.gz" | awk "{print \$1}"; }
        _uv_executable_sha256() { echo "0000000000000000000000000000000000000000000000000000000000000000"; }
        check_uv
    '

    assert_failure
    assert_output --partial "executable checksum mismatch"
    [[ ! -e "$HOME/.local/bin/uv" ]]
}

@test "check_uv rejects a symlink executable member in a checksum-valid archive" {
    repack_archive symlink

    run_verified_uv_check

    assert_failure
    assert_output --partial "expected regular executable"
}

@test "check_uv rejects a hardlink executable member in a checksum-valid archive" {
    repack_archive hardlink

    run_verified_uv_check

    assert_failure
    assert_output --partial "expected regular executable"
}

@test "check_uv rejects a special executable member in a checksum-valid archive" {
    repack_archive special

    run_verified_uv_check

    assert_failure
    assert_output --partial "expected regular executable"
}

@test "check_uv rejects duplicate executable members in a checksum-valid archive" {
    repack_archive duplicate

    run_verified_uv_check

    assert_failure
    assert_output --partial "exactly one expected executable"
}

@test "check_uv removes a previously installed uv when verification fails" {
    printf '#!/bin/sh\necho unverified\n' > "$HOME/.local/bin/uv"
    chmod +x "$HOME/.local/bin/uv"
    cat > "$SANDBOX/bin/curl" <<'EOF'
#!/bin/sh
exit 1

EOF
    chmod +x "$SANDBOX/bin/curl"

    run env PATH="$SANDBOX/bin:/usr/bin:/bin" HOME="$HOME" bash -c '
        print_step() { :; }; print_success() { :; }; print_warning() { :; }
        command_exists() { command -v "$1" >/dev/null 2>&1; }
        source "'"$INSTALL_LIB"'"
        if check_uv; then exit 99; fi
        test ! -e "$HOME/.local/bin/uv"
    '
    assert_success
}

@test "deploy consumers reject a fixed-path uv without this invocation's token" {
    printf '#!/bin/sh\necho unverified\n' > "$HOME/.local/bin/uv"
    chmod +x "$HOME/.local/bin/uv"

    run env PATH="$SANDBOX/bin:/usr/bin:/bin" HOME="$HOME" bash -c '
        source "'"$BATS_TEST_DIRNAME"'/../../bootstrap/lib/deploy.sh"
        manifest_uv_bin
    '
    assert_failure
}
