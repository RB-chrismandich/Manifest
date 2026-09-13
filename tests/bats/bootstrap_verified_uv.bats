#!/usr/bin/env bats

load '../test_helper/bats-support/load'
load '../test_helper/bats-assert/load'

INSTALL_LIB="$BATS_TEST_DIRNAME/../../bootstrap/lib/install.sh"

setup() {
    SANDBOX=$(mktemp -d "${BATS_TMPDIR:-/tmp}/manifest_uv.XXXXXX")
    export HOME="$SANDBOX/home"
    mkdir -p "$HOME/.local/bin" "$SANDBOX/bin" "$SANDBOX/release"
    target="aarch64-apple-darwin"
    mkdir -p "$SANDBOX/release/uv-$target"
    printf '#!/bin/sh\necho verified\n' > "$SANDBOX/release/uv-$target/uv"
    chmod +x "$SANDBOX/release/uv-$target/uv"
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

@test "check_uv replaces an ambient same-version binary with verified pinned bytes" {
    run env PATH="$SANDBOX/bin:/usr/bin:/bin" HOME="$HOME" PLATFORM=macos bash -c '
        print_step() { :; }; print_success() { :; }; print_warning() { echo "$*"; }
        command_exists() { command -v "$1" >/dev/null 2>&1; }
        source "'"$INSTALL_LIB"'"
        _uv_archive_sha256() { shasum -a 256 "'"$SANDBOX"'/release/archive.tar.gz" | awk "{print \$1}"; }
        check_uv
    '
    assert_success
    run "$HOME/.local/bin/uv"
    assert_success
    assert_output "verified"
}
