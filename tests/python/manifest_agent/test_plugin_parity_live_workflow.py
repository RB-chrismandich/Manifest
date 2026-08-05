"""Static release-artifact assertions for the protected live parity workflow."""

from __future__ import annotations

from pathlib import Path


def test_live_parity_workflow_builds_and_uploads_immutable_release_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github/workflows/plugin-parity-live.yml").read_text(
        encoding="utf-8"
    )

    assert "git archive" not in workflow
    assert "uv run python tools/build_manifest_release.py" in workflow
    assert "--output-dir live-release" in workflow
    assert '--archive-base-url "$ARCHIVE_BASE_URL"' in workflow
    assert (
        'ARCHIVE_BASE_URL="https://github.com/${GITHUB_REPOSITORY}/actions/runs/'
        '${GITHUB_RUN_ID}/artifacts"'
    ) in workflow
    assert "Verify immutable release metadata" in workflow
    assert 'metadata["commit"] == commit' in workflow
    assert "release commit differs from workflow commit" in workflow
    assert 'metadata["archive_sha256"] == checksum(archive.read_bytes())' in workflow
    assert "release archive checksum does not match metadata" in workflow
    assert (
        'sha256sum "$WHEEL" "$ARCHIVE" "$METADATA" | tee release-checksums.txt'
        in workflow
    )
    assert "live-release/manifest-plugins-*.tar.gz" in workflow
    assert "live-release/manifest-release.json" in workflow
    assert 'uvx --from "$WHEEL" manifest install' in workflow
    assert 'uvx --from "$WHEEL" manifest reconcile' in workflow
    assert 'uvx --from "$WHEEL" manifest uninstall' in workflow


def test_live_parity_workflow_embeds_a_strict_archive_verifier() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = (repo_root / ".github/workflows/plugin-parity-live.yml").read_text(
        encoding="utf-8"
    )
    marker = (
        'python3 - "$ARCHIVE" "$METADATA" "$GITHUB_SHA" "$ARCHIVE_BASE_URL" <<\'PY\'\n'
    )
    verifier = workflow.split(marker, 1)[1].split("          PY\n", 1)[0]
    verifier = "\n".join(
        line.removeprefix("          ") for line in verifier.splitlines()
    )

    compile(verifier, "plugin-parity-live-verifier", "exec")
    assert "DOMAIN_BUNDLES = (" in verifier
    assert "TOP_LEVEL_KEYS" in verifier
    assert "BUNDLE_KEYS" in verifier
    assert "FILE_KEYS" in verifier
    assert 'tarfile.open(archive, mode="r:gz")' in verifier
    assert "archive has duplicate member" in verifier
    assert "archive has unlisted member" in verifier
    assert "archive member mode differs" in verifier
    assert "set(observed) == set(files)" in verifier
    assert "bundle_checksum(name, files)" in verifier
    assert "release marketplace bundle set is invalid" in verifier
