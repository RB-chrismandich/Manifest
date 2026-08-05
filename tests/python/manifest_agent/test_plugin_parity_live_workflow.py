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
    assert 'metadata["commit"] != commit' in workflow
    assert (
        'metadata["archive_sha256"] != hashlib.sha256(archive.read_bytes()).hexdigest()'
        in workflow
    )
    assert (
        'sha256sum "$WHEEL" "$ARCHIVE" "$METADATA" | tee release-checksums.txt'
        in workflow
    )
    assert "live-release/manifest-plugins-*.tar.gz" in workflow
    assert "live-release/manifest-release.json" in workflow
    assert 'uvx --from "$WHEEL" manifest install' in workflow
    assert 'uvx --from "$WHEEL" manifest reconcile' in workflow
    assert 'uvx --from "$WHEEL" manifest uninstall' in workflow
