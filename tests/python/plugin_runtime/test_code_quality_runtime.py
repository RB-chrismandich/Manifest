"""Isolation tests for the installed manifest-code-quality bundle."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def code_quality_bundle(repo_root: Path) -> Path:
    return repo_root / "plugins" / "manifest-code-quality"


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    data = tmp_path / "data"
    config = tmp_path / "config"
    for path in (home, state, data, config):
        path.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_DATA_HOME": str(data),
        "XDG_CONFIG_HOME": str(config),
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": "",
    }


def _run(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", "-B", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_constitution_cli_loads_only_adjacent_json_policy(
    code_quality_bundle: Path, tmp_path: Path
) -> None:
    skill = code_quality_bundle / "skills/code-audit-constitution"
    script = skill / "scripts/constitution_check.py"

    help_result = _run(script, "--help", env=_isolated_env(tmp_path), cwd=tmp_path)
    list_result = _run(script, "--list", env=_isolated_env(tmp_path), cwd=tmp_path)

    assert help_result.returncode == 0, help_result.stderr
    assert list_result.returncode == 0, list_result.stderr
    assert "CON-013" in list_result.stdout
    assert (skill / "config/code_constitution.json").is_file()
    assert (skill / "config/constitution_baseline.json").is_file()
    registry = skill / "scripts/constitution/registry.py"
    source = registry.read_text(encoding="utf-8")
    assert "import yaml" not in source
    assert "code_constitution.yml" not in source
    assert "configs/claude" not in source


def test_smoke_cli_uses_adjacent_vendored_yaml_offline(
    code_quality_bundle: Path, tmp_path: Path
) -> None:
    skill = code_quality_bundle / "skills/smoke-manage"
    script = skill / "scripts/smoke.py"
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "demo.yaml").write_text(
        "version: 1\napp: demo\ntests: []\n", encoding="utf-8"
    )

    help_result = _run(script, "--help", env=_isolated_env(tmp_path), cwd=tmp_path)
    list_result = _run(
        script,
        "list",
        "--app",
        "demo",
        "--json",
        "--catalog-dir",
        str(catalog_dir),
        env=_isolated_env(tmp_path),
        cwd=tmp_path,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert list_result.returncode == 0, list_result.stderr
    assert json.loads(list_result.stdout) == {"demo": []}
    assert "manifest_cli" not in help_result.stderr
    assert (skill / "vendor/yaml/__init__.py").is_file()
    assert (skill / "vendor/LICENSE.PyYAML").is_file()


def test_vendored_yaml_provenance_matches_lock_and_committed_hashes(
    repo_root: Path, code_quality_bundle: Path, tmp_path: Path
) -> None:
    vendor = code_quality_bundle / "skills/smoke-manage/vendor"
    metadata = json.loads((vendor / "VENDOR.json").read_text(encoding="utf-8"))

    assert metadata["name"] == "PyYAML"
    assert metadata["version"] == "6.0.3"
    assert metadata["source"] == "https://pypi.org/project/PyYAML/6.0.3/"
    assert metadata["sdist_sha256"] == (
        "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f"
    )
    assert metadata["license"] == "MIT"
    assert metadata["files"]

    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-B",
            str(repo_root / "tools/vendor_bundle_dependencies.py"),
            "--check",
        ],
        cwd=tmp_path,
        env=_isolated_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("bad_member", "message"),
    [
        ("lib/yaml/_yaml.cpython-313-darwin.so", "native"),
        ("lib/yaml/unexpected.py", "unexpected"),
    ],
)
def test_vendor_tool_rejects_native_and_unexpected_archive_members(
    repo_root: Path, bad_member: str, message: str
) -> None:
    tool = repo_root / "tools/vendor_bundle_dependencies.py"
    spec = importlib.util.spec_from_file_location("vendor_bundle_dependencies", tool)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    archive = BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as handle:
        for name in (
            f"pyyaml-6.0.3/{bad_member}",
            "pyyaml-6.0.3/LICENSE",
        ):
            info = tarfile.TarInfo(name)
            info.size = 1
            handle.addfile(info, BytesIO(b"x"))
    archive.seek(0)

    with (
        tarfile.open(fileobj=archive, mode="r:gz") as handle,
        pytest.raises(module.VendorError, match=message),
    ):
        module._validated_members(handle, "pyyaml-6.0.3")


def test_scaffold_and_audit_assets_are_bundle_local_and_exact(
    repo_root: Path, code_quality_bundle: Path
) -> None:
    compatibility = repo_root / "templates/scaffold"
    packaged = code_quality_bundle / "skills/project-scaffold/templates"
    expected = {
        path.relative_to(compatibility): path.read_bytes()
        for path in compatibility.rglob("*")
        if path.is_file()
    }
    actual = {
        path.relative_to(packaged): path.read_bytes()
        for path in packaged.rglob("*")
        if path.is_file()
    }

    assert actual == expected
    assert (
        code_quality_bundle / "skills/code-audit/references/antipatterns.md"
    ).read_bytes() == (
        repo_root / "configs/claude/references/antipatterns.md"
    ).read_bytes()


def test_code_quality_contract_declares_every_runtime_asset(
    code_quality_bundle: Path,
) -> None:
    contract = load_contract(code_quality_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        "skills/code-audit-constitution/scripts",
        "skills/code-audit-constitution/config",
        "skills/code-audit-constitution/references",
        "skills/smoke-manage/scripts",
        "skills/smoke-manage/vendor",
        "skills/project-scaffold/templates",
        "skills/code-audit/references",
    }
    assert set(contract.capabilities.executables[CapabilityTier.OPTIONAL]) == {
        "browser-use",
        "playwright",
        "semgrep",
    }
    assert contract.capabilities.executables[CapabilityTier.REQUIRED] == (
        "git",
        "python3",
    )


def test_code_quality_skills_do_not_call_legacy_shared_runtimes(
    code_quality_bundle: Path,
) -> None:
    forbidden = (
        "configs/claude/scripts",
        "~/.claude/scripts",
        "manifest smoke",
        "parallel_agent.py",
        "learning_capture.sh",
    )

    for skill in code_quality_bundle.glob("skills/*/SKILL.md"):
        source = skill.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{skill}: forbidden runtime marker {marker}"
