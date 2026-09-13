# shellcheck shell=bash
# Verified uv release bootstrap. Sourced by install.sh after output helpers load.
export MANIFEST_VERIFIED_UV_BIN=""
export MANIFEST_VERIFIED_UV_TOKEN=""
UV_INSTALLER_PINNED_VERSION=0.12.6

invalidate_verified_uv() {
    MANIFEST_VERIFIED_UV_BIN=""
    MANIFEST_VERIFIED_UV_TOKEN=""
    rm -f "$HOME/.local/bin/uv" "$HOME/.local/bin/uvx"
}

_uv_release_target() {
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) echo "aarch64-apple-darwin" ;;
        Darwin-x86_64) echo "x86_64-apple-darwin" ;;
        Linux-x86_64) echo "x86_64-unknown-linux-gnu" ;;
        Linux-aarch64 | Linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
        *) echo "" ;;
    esac
}

_uv_archive_sha256() {
    case "$1" in
        x86_64-unknown-linux-gnu) echo "8681d8921e7d520fb368991dcf5f9c1905b80f5bf2a265a0ed085c8d8e342477" ;;
        aarch64-unknown-linux-gnu) echo "d58030acd26159499ac82f32da12d1b3c12a3a1bfc414232d9082070c03e128d" ;;
        aarch64-apple-darwin) echo "14b459d51ea2e71eeba28c45a268c922bdf8607fc6455e3f40b4e082895d160d" ;;
        x86_64-apple-darwin) echo "2a26ea71bbeff1c7e12c2cc40245c96a041deff276bc921e7038e304d5d3e04c" ;;
        *) echo "" ;;
    esac
}

_uv_executable_sha256() {
    case "$1" in
        x86_64-unknown-linux-gnu) echo "d381f11517c66523211b0876552ff7dea5c1b4b0f13800571b35225761302fba" ;;
        aarch64-unknown-linux-gnu) echo "bbefb544cf8398f079cee46dc051a60b132139a3cc0b0cf19fab2984d98ece1f" ;;
        aarch64-apple-darwin) echo "e8929237934c8679686428f5a7736c7ae7a5fe7a33b0504d1b03446cdbc43c94" ;;
        x86_64-apple-darwin) echo "08b4ee2e5f04250ffe2231ffc07ed6961568c81c2e7f275b71b379a5bd06fb1e" ;;
        *) echo "" ;;
    esac
}

_uv_archive_member() {
    case "$1" in
        x86_64-unknown-linux-gnu | aarch64-unknown-linux-gnu | aarch64-apple-darwin | x86_64-apple-darwin) printf 'uv-%s/uv\n' "$1" ;;
        *) printf '\n' ;;
    esac
}

install_uv_verified_release() (
    local target sha_tool expected archive member workdir actual members candidate_count metadata
    target="$(_uv_release_target)"
    if [[ -z "$target" ]]; then
        print_warning "uv: no known release target for $(uname -s)/$(uname -m)"
        return 1
    fi
    if command_exists sha256sum; then sha_tool="sha256sum"; elif command_exists shasum; then sha_tool="shasum -a 256"; else
        print_warning "uv: cannot verify a checksum without sha256sum or shasum"
        return 1
    fi
    expected="$(_uv_archive_sha256 "$target")"
    member="$(_uv_archive_member "$target")"
    if [[ -z "$expected" || -z "$member" ]]; then
        print_warning "uv: no committed archive metadata for $target"
        return 1
    fi
    local base="https://github.com/astral-sh/uv/releases/download/${UV_INSTALLER_PINNED_VERSION}"
    archive="uv-${target}.tar.gz"
    workdir="$(mktemp -d)" || return 1
    chmod 700 "$workdir"
    trap 'rm -rf "$workdir"' EXIT
    if ! curl -fsSL -o "$workdir/$archive" "$base/$archive"; then
        print_warning "uv: could not download $archive"
        return 1
    fi
    actual="$(cd "$workdir" && $sha_tool "$archive" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        print_warning "uv: checksum mismatch for $archive (want $expected, got $actual)"
        return 1
    fi
    members="$(tar -tzf "$workdir/$archive")" || {
        print_warning "uv: could not inspect $archive"
        return 1
    }
    while IFS= read -r entry; do case "$entry" in /* | ../* | */../* | .. | */..)
        print_warning "uv: archive contains unsafe member path"
        return 1
        ;;
    esac done <<< "$members"
    candidate_count="$(printf '%s\n' "$members" | awk -v member="$member" '$0 == member { count++ } END { print count + 0 }')"
    if [[ "$candidate_count" -ne 1 ]]; then
        print_warning "uv: archive must contain exactly one expected executable member"
        return 1
    fi
    metadata="$(tar -tvzf "$workdir/$archive" -- "$member")" || {
        print_warning "uv: could not inspect expected executable member"
        return 1
    }
    if [[ "${metadata:0:1}" != "-" ]]; then
        print_warning "uv: expected regular executable member"
        return 1
    fi
    mkdir -p "$workdir/extract"
    chmod 700 "$workdir/extract"
    if ! tar -xzf "$workdir/$archive" -C "$workdir/extract" -- "$member"; then
        print_warning "uv: could not extract expected executable member"
        return 1
    fi
    local extracted="$workdir/extract/$member"
    if [[ ! -f "$extracted" || -L "$extracted" || ! -x "$extracted" ]]; then
        print_warning "uv: expected regular executable member"
        return 1
    fi
    local bin_dir="$HOME/.local/bin" installed temp_binary expected_binary
    mkdir -p "$bin_dir"
    temp_binary="$(mktemp "$bin_dir/.uv.XXXXXX")" || return 1
    if ! install -m 755 "$extracted" "$temp_binary"; then
        rm -f "$temp_binary"
        print_warning "uv: could not stage verified executable"
        return 1
    fi
    if ! mv -f "$temp_binary" "$bin_dir/uv"; then
        rm -f "$temp_binary"
        print_warning "uv: could not install verified executable"
        return 1
    fi
    expected_binary="$(_uv_executable_sha256 "$target")"
    installed="$($sha_tool "$bin_dir/uv" | awk '{print $1}')"
    if [[ -n "$expected_binary" && "$installed" != "$expected_binary" ]]; then
        rm -f "$bin_dir/uv"
        print_warning "uv: executable checksum mismatch for $target"
        return 1
    fi
)

check_uv() {
    MANIFEST_VERIFIED_UV_BIN=""
    print_step "Installing verified pinned uv release..."
    if ! command_exists curl; then
        invalidate_verified_uv
        print_warning "uv: curl is required to download the verified pinned release"
        return 1
    fi
    if ! install_uv_verified_release; then
        invalidate_verified_uv
        print_warning "Could not install verified pinned uv; see https://docs.astral.sh/uv/"
        return 1
    fi
    if [[ ! -x "$HOME/.local/bin/uv" ]]; then
        invalidate_verified_uv
        print_warning "uv: verified install did not produce ~/.local/bin/uv"
        return 1
    fi
    MANIFEST_VERIFIED_UV_BIN="$HOME/.local/bin/uv"
    MANIFEST_VERIFIED_UV_TOKEN="sha256:$(_uv_executable_sha256 "$(_uv_release_target)")"
    print_success "uv installed from verified pinned release bytes"
}
