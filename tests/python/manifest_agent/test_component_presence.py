"""Directory-valued declared components must produce adapter evidence.

Regression pin for the codex reconcile deadlock found on 2026-08-24: 37 of the
71 components declared across `plugins/*/plugin.json` name a DIRECTORY
(`skills/*/scripts`, `.../references`, `.../templates`, `.../vendor`), but
`_add_installed_file_evidence` only recorded evidence for paths passing
`Path.is_file()`. Every directory-valued component was therefore reported as
`missing adapter evidence: <bundle>:runtime:<id>` even when the directory was
installed and populated, which pins the harness at BLOCKED forever — no state
repair can clear it because the check can never pass.

An EMPTY directory is deliberately still not evidence: the component declares
content that must be installed, and an incidentally-created empty dir is not
that. Only a directory containing at least one file counts.
"""

from pathlib import Path

import pytest

from manifest_agent.adapters.base import collect_native_component_evidence
from manifest_agent.adapters.component_presence import component_is_installed
from manifest_agent.contracts import (
    Capabilities,
    CompatibilityStatus,
    Component,
    Components,
    Provenance,
)
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    DesiredState,
    MarketplaceSource,
    MarketplaceSourceKind,
)


def _contract() -> BundleContract:
    return BundleContract(
        name="manifest-workspace",
        version="0.2.0",
        description="fixture",
        category="productivity",
        components=Components(
            skills_root="skills",
            skills_include=("*/SKILL.md",),
            agents=(),
            hooks=(),
            guidance=(),
            runtime=(
                Component("catalog", "runtime/catalog.py"),
                Component("agent-scripts", "skills/parallel-agent/scripts"),
                Component("empty-dir", "runtime/empty"),
            ),
        ),
        capabilities=Capabilities(
            mcp=dict.fromkeys(CapabilityTier, ()),
            executables=dict.fromkeys(CapabilityTier, ()),
        ),
        compatibility={"codex": CompatibilityStatus("native")},
        provenance=Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
    )


def _desired(root: Path) -> DesiredState:
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source="fixture",
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(root), None
        ),
        release_root=root,
        repository_url="https://example.invalid/repo",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=(_contract(),),
        selected_optional=frozenset(),
        requested_harnesses=("codex",),
    )


def _evidence(desired: DesiredState, root: Path) -> set[str]:
    return collect_native_component_evidence(
        desired, {"manifest-workspace": root}, {}, lambda _name: None
    )


@pytest.fixture
def installed(tmp_path: Path) -> tuple[DesiredState, Path]:
    """Build a source tree and an identical installed plugin root."""
    for base in (tmp_path / "plugins" / "manifest-workspace", tmp_path / "installed"):
        (base / "runtime").mkdir(parents=True)
        (base / "runtime" / "catalog.py").write_text("x = 1\n", encoding="utf-8")
        scripts = base / "skills" / "parallel-agent" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (base / "runtime" / "empty").mkdir()
    return _desired(tmp_path), tmp_path / "installed"


def test_directory_component_with_content_is_evidence(
    installed: tuple[DesiredState, Path],
) -> None:
    desired, root = installed

    evidence = _evidence(desired, root)

    assert "manifest-workspace:runtime:agent-scripts" in evidence


def test_file_component_remains_evidence(
    installed: tuple[DesiredState, Path],
) -> None:
    desired, root = installed

    evidence = _evidence(desired, root)

    assert "manifest-workspace:runtime:catalog" in evidence


def test_empty_directory_component_is_not_evidence(
    installed: tuple[DesiredState, Path],
) -> None:
    desired, root = installed

    evidence = _evidence(desired, root)

    assert "manifest-workspace:runtime:empty-dir" not in evidence


def test_absent_directory_component_is_not_evidence(
    installed: tuple[DesiredState, Path],
) -> None:
    desired, root = installed
    # The source declares it, but this install never received it.
    for path in sorted(
        (root / "skills" / "parallel-agent" / "scripts").iterdir(), reverse=True
    ):
        path.unlink()
    (root / "skills" / "parallel-agent" / "scripts").rmdir()

    evidence = _evidence(desired, root)

    assert "manifest-workspace:runtime:agent-scripts" not in evidence


def test_component_is_installed_accepts_populated_directory(tmp_path: Path) -> None:
    target = tmp_path / "scripts"
    target.mkdir()
    (target / "run.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert component_is_installed(target) is True


def test_component_is_installed_rejects_empty_directory(tmp_path: Path) -> None:
    target = tmp_path / "empty"
    target.mkdir()

    assert component_is_installed(target) is False


def test_component_is_installed_rejects_absent_path(tmp_path: Path) -> None:
    assert component_is_installed(tmp_path / "nope") is False
