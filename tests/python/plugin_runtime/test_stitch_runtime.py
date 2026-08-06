"""Isolation tests for the installed stitch-design bundle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def stitch_bundle(repo_root: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "stitch-design"
    shutil.copytree(
        repo_root / "plugins/stitch-design",
        installed,
        ignore=shutil.ignore_patterns("node_modules"),
    )
    return installed


def _offline_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "npm_config_offline": "true",
        "NO_PROXY": "*",
    }


def _run_node(
    script: Path, *args: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None
    return subprocess.run(
        [node, str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generated_validators_run_offline_without_node_modules(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    component = tmp_path / "Card.tsx"
    component.write_text(
        "export interface CardProps { readonly title: string }\n"
        "export function Card(props: CardProps) { return <section>{props.title}</section> }\n",
        encoding="utf-8",
    )
    validator = stitch_bundle / "skills/react-components/scripts/validate.js"
    result = _run_node(
        validator, str(component), cwd=tmp_path, env=_offline_env(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    assert "COMPONENT VALID" in result.stdout
    assert not (stitch_bundle / "node_modules").exists()


def test_generated_native_validator_runs_offline_without_node_modules(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    component = tmp_path / "Card.tsx"
    component.write_text(
        "export interface CardProps { readonly title: string }\n"
        "export function Card(props: CardProps) { return <Text>{props.title}</Text> }\n",
        encoding="utf-8",
    )
    validator = stitch_bundle / "skills/react-native/scripts/validate.js"
    result = _run_node(
        validator, str(component), cwd=tmp_path, env=_offline_env(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    assert "COMPONENT VALID" in result.stdout


@pytest.mark.parametrize(
    "artifact",
    ("extract-inline-html", "post-process", "snapshot", "validate-react"),
)
def test_generated_artifacts_are_standalone_and_include_notices(
    stitch_bundle: Path, tmp_path: Path, artifact: str
) -> None:
    script = stitch_bundle / f"runtime/dist/{artifact}.mjs"
    source = script.read_text(encoding="utf-8")
    assert "THIRD-PARTY LICENSE NOTICES" in source
    result = _run_node(script, "--help", cwd=tmp_path, env=_offline_env(tmp_path))
    assert result.returncode == 0, result.stderr
    if artifact in {"extract-inline-html", "post-process", "snapshot"}:
        assert f"node runtime/dist/{artifact}.mjs" in result.stdout
        assert "<BUNDLE_ROOT>" not in result.stdout


def test_snapshot_reports_missing_optional_chromium(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    snapshot = stitch_bundle / "runtime/dist/snapshot.mjs"
    result = _run_node(
        snapshot,
        "--url",
        "http://127.0.0.1:65534",
        "--chromium",
        str(tmp_path / "missing-chromium"),
        "--output",
        str(tmp_path / "page.html"),
        cwd=tmp_path,
        env=_offline_env(tmp_path),
    )

    assert result.returncode != 0
    assert "chromium" in result.stderr.lower()
    assert "download" not in result.stderr.lower()


def test_stitch_build_dependencies_are_exact_and_checked_in(
    stitch_bundle: Path,
) -> None:
    package = json.loads((stitch_bundle / "runtime/node/package.json").read_text())
    lock = json.loads((stitch_bundle / "runtime/node/package-lock.json").read_text())

    assert set(package["devDependencies"]) == {
        "@babel/generator",
        "@babel/parser",
        "@babel/traverse",
        "esbuild",
        "puppeteer-core",
    }
    assert all(
        not version.startswith(("^", "~", ">", "<"))
        for version in package["devDependencies"].values()
    )
    assert lock["lockfileVersion"] == 3
    assert not list(stitch_bundle.rglob("node_modules"))
    assert not (stitch_bundle / "skills/react-components/package.json").exists()
    assert not (stitch_bundle / "skills/react-components/package-lock.json").exists()
    assert not (stitch_bundle / "skills/react-native/package.json").exists()


def test_stitch_docs_use_bundle_paths_and_qualified_skills(stitch_bundle: Path) -> None:
    forbidden = (
        "configs/claude",
        "stitch-utilities",
        "stitch-skills/plugins",
        "npx skills add",
        "manifest parallel-agent",
    )
    for document in [
        *stitch_bundle.glob("skills/*/SKILL.md"),
        *stitch_bundle.glob("skills/*/README.md"),
    ]:
        source = document.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{document}: forbidden marker {marker}"

    shadcn_readme = (stitch_bundle / "skills/shadcn-ui/README.md").read_text()
    assert "../../CONTRIBUTING.md" not in shadcn_readme
    assert "../../LICENSE" not in shadcn_readme
    assert (stitch_bundle / "manifest-capabilities.yml").is_file()


def test_stitch_contract_declares_generated_runtime(stitch_bundle: Path) -> None:
    contract = load_contract(stitch_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        "runtime/dist",
        "runtime/node/build.mjs",
        "runtime/node/package-lock.json",
        "runtime/node/package.json",
        "skills/extract-static-html/scripts",
        "skills/react-components/scripts",
        "skills/react-native/scripts",
    }
    assert contract.capabilities.mcp[CapabilityTier.OPTIONAL] == ("stitch",)
    assert contract.capabilities.executables[CapabilityTier.OPTIONAL] == (
        "chromium",
        "curl",
    )
