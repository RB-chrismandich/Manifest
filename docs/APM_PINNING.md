# The pinned `apm` version

> How Manifest pins, verifies, and upgrades the `apm` binary.

**Last Updated**: 2026-07-30
**Audience**: contributors touching the apm install path
**Status**: **scheduled for retirement.** Spec 674 Phase 5 (T5.4) retires this
whole apparatus once the plugin cutover completes — the pinned-wheel install
path, `apm_publish_gate.sh`, `apm_install_verify.sh`, `apm_hash_lib.sh`,
`apm_pin_verified.txt`, and the CI gitleaks-presence check that exists only so
the publish gate fails closed. It is split out of
[DEPLOY_OWNERSHIP.md](DEPLOY_OWNERSHIP.md) so that retirement is one file, not a
section to excise.

---

`apm` is pinned by version **and** sha256 in `bootstrap/lib/install.sh`, and
installed fail-closed: a checksum mismatch, a failed download, or a missing
checksum tool leaves apm uninstalled rather than falling back to an unverified
binary.

The digest is not a corruption check — it is the **provenance**. PyPI ties
`apm-cli` to no repository (no `home_page`, no `project_urls`, no author), so
the digest recorded at verification time is the only thing asserting the
artifact's identity.

### Upgrading

Bumping the version without re-recording the digest silently disables the only
check there is, so the pin is gated:

1. Re-run the deployment matrix against the new version in an isolated HOME.
2. Confirm idempotence — install twice, assert byte-identical.
3. Confirm equivalence — the new version's output matches the old one's for an
   unchanged source tree.
4. Update **both** `bootstrap/lib/install.sh` and
   `configs/claude/config/apm_pin_verified.txt`.

`tests/bats/apm_upgrade_gate.bats` fails if the two disagree. That forces a bump
to arrive with an explicit "I re-verified this" — it cannot prove you ran steps
1–3, and its own record file says so.

### Offline / air-gapped install

```bash
APM_WHEEL_LOCAL=/path/to/apm_cli-0.26.0-py3-none-any.whl ./bootstrap.sh --enable-apm
```

Skips resolution and download entirely — no network, no registry. **The checksum
is still verified**: bringing your own file is not evidence about what is in it,
and an air-gapped install is exactly when nobody is watching. A missing local
artifact is an error, never a silent fallback to the network.
