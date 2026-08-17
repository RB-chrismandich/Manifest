"""Static safety assertions for the permanent manifest release workflow."""

from __future__ import annotations

import re
from pathlib import Path

from manifest_agent.contracts import DOMAIN_BUNDLES


def _workflow() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    return (repo_root / ".github/workflows/manifest-release.yml").read_text(
        encoding="utf-8"
    )


def test_release_trigger_only_watches_canonical_bundles() -> None:
    workflow = _workflow()

    assert "      - 'plugins/**'" not in workflow
    for bundle in DOMAIN_BUNDLES:
        assert f"      - 'plugins/{bundle}/**'" in workflow
    for excluded in (
        "adversarial-design-loop",
        "manifest-delegate",
        "manifest-docker",
    ):
        assert f"plugins/{excluded}/**" not in workflow


def test_release_uses_canonical_version_and_download_root() -> None:
    workflow = _workflow()

    assert 'VERSION="$(python3 -c' in workflow
    assert '["version"]' in workflow
    assert "refs/tags/${VERSION}" in workflow
    assert "releases/download/${VERSION}" not in workflow
    assert (
        '--archive-base-url "https://github.com/${GITHUB_REPOSITORY}/releases/download"'
        in workflow
    )
    assert "bump_apm_version.sh" not in workflow
    assert "git push origin main" not in workflow


def test_release_dependency_and_publication_are_reproducible_and_resumable() -> None:
    workflow = _workflow()

    assert re.search(r"astral-sh/setup-uv@[0-9a-f]{40}", workflow)
    assert re.search(r'(?<!-)version: "\d+\.\d+(\.\d+)?"', workflow)
    assert "pip install uv" not in workflow
    assert 'echo "state=draft"' in workflow
    assert 'echo "state=published"' in workflow
    assert 'echo "state=absent"' in workflow
    assert 'gh release create "$VERSION"' in workflow
    assert "--draft" in workflow
    assert "--verify-tag" in workflow
    assert 'gh release upload "$VERSION" --clobber' in workflow
    assert 'gh release edit "$VERSION" --draft=false' in workflow
