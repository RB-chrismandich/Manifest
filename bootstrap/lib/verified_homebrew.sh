# shellcheck shell=bash
# Stage-one Homebrew installer pin. Provenance/update procedure: verified_homebrew.md.

_homebrew_installer_sha256() {
    printf '%s\n' '151a786c066af55f61bd32bd4804470fdb2b872e6a42a8ef1335c29760e37404'
}

install_homebrew_verified() (
    local commit='df3c2556141c012eaba0453ede7a1bd4f05b824c'
    local workdir installer actual expected sha_tool
    if command_exists sha256sum; then sha_tool=sha256sum; elif command_exists shasum; then sha_tool=shasum; else
        print_error "Homebrew: cannot verify installer without sha256sum or shasum"
        return 1
    fi
    umask 077
    workdir="$(mktemp -d "${TMPDIR:-/tmp}/manifest-homebrew.XXXXXX")" || return 1
    trap 'rm -rf "$workdir"' EXIT
    chmod 700 "$workdir" || return 1
    installer="$workdir/install.sh"
    if ! curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL \
        -o "$installer" "https://raw.githubusercontent.com/Homebrew/install/$commit/install.sh"; then
        print_error "Homebrew: installer download failed"
        return 1
    fi
    if [[ ! -f "$installer" || -L "$installer" ]]; then
        print_error "Homebrew: download did not produce a regular installer"
        return 1
    fi
    if [[ "$sha_tool" == sha256sum ]]; then
        actual="$(sha256sum "$installer")" || return 1
    else
        actual="$(shasum -a 256 "$installer")" || return 1
    fi
    actual="${actual%% *}"
    expected="$(_homebrew_installer_sha256)" || return 1
    if [[ "$actual" != "$expected" ]]; then
        print_error "Homebrew: installer checksum mismatch"
        return 1
    fi
    /bin/bash "$installer"
)
