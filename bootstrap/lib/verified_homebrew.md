<!-- doc-type: reference -->
# Homebrew installer pin

`verified_homebrew.sh` verifies the initial installer before executing it. The
existing macOS consent prompt, Homebrew interaction, Intel/Apple Silicon setup,
and Linux package-manager paths remain unchanged.

Pin recorded on 2026-10-30. This is the last mainline revision before the upstream
Intel-removal merge, selected to retain the bootstrap's Intel and Apple Silicon
installer paths. Its platform-selection block sets `/opt/homebrew` for arm64 and
`/usr/local` for Intel; the newer current upstream installer rejects Intel.
Subsequent Homebrew components may independently change platform support.

Pinned artifact:

- Official source: [Homebrew/install](https://github.com/Homebrew/install), linked
  by [brew.sh](https://brew.sh/).
- Commit: [`df3c2556141c012eaba0453ede7a1bd4f05b824c`](https://github.com/Homebrew/install/commit/df3c2556141c012eaba0453ede7a1bd4f05b824c).
- File: [`install.sh`](https://raw.githubusercontent.com/Homebrew/install/df3c2556141c012eaba0453ede7a1bd4f05b824c/install.sh).
  Size: 33,763 bytes.
- Git blob: `473f31b90873ff25018ed7b086ee60c567910b37`.
- SHA-256: `151a786c066af55f61bd32bd4804470fdb2b872e6a42a8ef1335c29760e37404`.

The commit was fetched from the official Git repository without checking out or
executing its scripts. `git show <commit>:install.sh` and a separate HTTPS raw
request addressed by that full commit produced byte-identical files and the
same SHA-256; Git object integrity was checked with `git fsck`. The official
repository identity and selected installer control flow were inspected. No
independent maintainer signature verification is claimed.

To update, select and inspect an official immutable commit supporting both architectures,
compare its Git blob
with the commit-addressed download, calculate SHA-256 locally, then change the
commit, committed digest and this record together in review. Never fetch an
expected digest alongside the installer at bootstrap execution time. Run the
offline `tests/bats/bootstrap_verified_homebrew.bats` suite after updating.

This pins only the initial installer. The upstream script still fetches Homebrew
repositories/tags and runs `brew update`, and respects upstream environment
configuration. It does not pin the complete Homebrew installation or eliminate
trust in subsequent Homebrew supply-chain operations. Temporary staging is
private and removed on exit; checksum/download/installer failures stop bootstrap
before reporting installation success. Tests use synthetic local installers;
actual Homebrew installation and macOS execution are not part of verification.
